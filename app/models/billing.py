"""Invoices, invoice items and payments.

Financial values are always recalculated server-side from database service
prices; finalized invoices are immutable (cancel instead of delete).
"""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, Index

from app.extensions import db
from app.models.user import TimestampMixin

TWO_PLACES = Decimal("0.01")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

INVOICE_STATUSES = [
    ("draft", "Draft"),
    ("finalized", "Finalized"),
    ("partially_paid", "Partially Paid"),
    ("paid", "Paid"),
    ("cancelled", "Cancelled"),
]

PAYMENT_METHODS = [
    ("cash", "Cash"),
    ("upi", "UPI"),
    ("card", "Card"),
    ("bank_transfer", "Bank Transfer"),
    ("other", "Other"),
]


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class Invoice(db.Model, TimestampMixin):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    invoice_code = db.Column(db.String(40), unique=True, nullable=False, index=True)

    patient_id = db.Column(
        db.Integer, db.ForeignKey("patients.id"), nullable=False
    )
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"))

    status = db.Column(db.String(20), default="draft", nullable=False, index=True)

    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    other_charges = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    grand_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    balance_due = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    notes = db.Column(db.Text)
    terms_snapshot = db.Column(db.Text)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    finalized_at = db.Column(db.DateTime)
    finalized_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    cancelled_at = db.Column(db.DateTime)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    cancel_reason = db.Column(db.String(255))
    pdf_file = db.Column(db.String(255))

    patient = db.relationship("Patient", back_populates="invoices")
    booking = db.relationship("Booking", back_populates="invoices")
    items = db.relationship(
        "InvoiceItem", back_populates="invoice",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="InvoiceItem.id",
    )
    payments = db.relationship(
        "Payment", back_populates="invoice", lazy="selectin",
        order_by="Payment.paid_at",
    )
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_invoices_status_created", "status", "created_at"),
        Index("ix_invoices_patient", "patient_id"),
    )

    # -- derived ---------------------------------------------------------
    @property
    def status_label(self):
        return dict(INVOICE_STATUSES).get(self.status, self.status.title())

    @property
    def paid_amount(self) -> Decimal:
        return money(self.amount_paid)

    @property
    def balance_amount(self) -> Decimal:
        return money(self.balance_due)

    @property
    def payment_method_display(self):
        methods = [p.method_label for p in self.payments]
        return ", ".join(dict.fromkeys(methods)) or "\u2014"

    def recalculate(self):
        """Recompute totals from items. Items' rates/taxes come from DB."""
        subtotal = Decimal("0")
        discount = Decimal("0")
        tax = Decimal("0")
        for item in self.items:
            line_gross = money(item.rate) * int(item.qty)
            item.line_subtotal = money(line_gross)
            item.tax_amount = money(line_gross * Decimal(str(item.tax_percent)) / 100)
            item.line_total = money(item.line_subtotal + item.tax_amount - money(item.discount_amount))
            subtotal += line_gross
            discount += money(item.discount_amount)
            tax += item.tax_amount
        other = money(self.other_charges)
        self.subtotal = money(subtotal)
        self.discount_amount = money(discount)
        self.tax_total = money(tax)
        grand = subtotal - discount + tax + other
        self.grand_total = money(grand)
        # Query payments directly from DB (relationship cache may be stale)
        paid = Decimal(str(
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.invoice_id == self.id)
            .scalar() or 0
        ))
        self.amount_paid = money(paid)
        self.balance_due = money(grand - paid)
        # auto status transitions (only when not draft/cancelled)
        if self.status in {"finalized", "partially_paid", "paid"}:
            if paid <= 0:
                self.status = "finalized"
            elif paid < self.grand_total:
                self.status = "partially_paid"
            else:
                self.status = "paid"

    def finalize(self, user_id=None):
        if self.status != "draft":
            raise ValueError("Only draft invoices can be finalized")
        if not self.items:
            raise ValueError("Cannot finalize an invoice without items")
        self.recalculate()
        self.status = "finalized" if self.amount_paid <= 0 else self.status
        now = utcnow()
        self.finalized_at = now
        self.finalized_by_id = user_id

    def cancel(self, reason, user_id=None):
        if self.status == "cancelled":
            raise ValueError("Invoice already cancelled")
        self.status = "cancelled"
        self.cancelled_at = utcnow()
        self.cancelled_by_id = user_id
        self.cancel_reason = reason[:250]

    def add_payment(self, amount, method, received_by=None, reference_no=None, notes=None):
        amount = money(amount)
        if amount <= 0:
            raise ValueError("Payment must be positive")
        if self.status == "cancelled":
            raise ValueError("Cannot pay a cancelled invoice")
        if self.status == "draft":
            raise ValueError("Finalize the invoice before recording payment")
        total_due = money(self.grand_total) - money(self.amount_paid)
        if amount > total_due and total_due > 0:
            raise ValueError(f"Amount exceeds balance due (\u20b9{total_due})")
        payment = Payment(
            invoice_id=self.id,
            amount=amount,
            method=method,
            reference_no=reference_no,
            notes=notes,
            received_by_id=received_by,
            paid_at=utcnow(),
        )
        db.session.add(payment)
        db.session.flush()
        self.recalculate()
        return payment

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.invoice_code,
            "patient": self.patient.full_name if self.patient else "",
            "grand_total": float(self.grand_total),
            "balance": float(self.balance_due),
            "status": self.status,
        }

    def __repr__(self):  # pragma: no cover
        return f"<Invoice {self.invoice_code} {self.status}>"


class InvoiceItem(db.Model, TimestampMixin):
    __tablename__ = "invoice_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(
        db.Integer, db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)

    service_name_snapshot = db.Column(db.String(128), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    rate = db.Column(db.Numeric(10, 2), nullable=False)  # snapshot from DB price
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tax_percent = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    line_subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    invoice = db.relationship("Invoice", back_populates="items")
    service = db.relationship("Service")


class Payment(db.Model, TimestampMixin):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(
        db.Integer, db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False)  # cash/upi/card/bank_transfer/other
    reference_no = db.Column(db.String(64))
    notes = db.Column(db.String(255))
    received_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    paid_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    invoice = db.relationship("Invoice", back_populates="payments")
    received_by = db.relationship("User")

    @property
    def method_label(self):
        return dict(PAYMENT_METHODS).get(self.method, self.method.title())
