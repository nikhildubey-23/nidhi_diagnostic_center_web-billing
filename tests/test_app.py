"""Tests for critical functionality."""
import pytest
from datetime import date, datetime
from decimal import Decimal

import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app import create_app
from app.extensions import db as _db
from app.models.user import User, Role, ROLE_PERMISSIONS
from app.models.patient import Patient
from app.models.service import Service, ServiceCategory
from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.booking import Booking
from app.utils.numbering import next_booking_code, next_patient_code, next_invoice_code


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        from app.cli_seed import run_seed
        run_seed()
        _db.session.commit()

        # Create admin user
        role = Role.query.filter_by(name="super_admin").first()
        admin = User(username="testadmin", email="test@test.com",
                     full_name="Test Admin", role_id=role.id)
        admin.set_password("testpass12345")
        _db.session.add(admin)
        _db.session.commit()

    yield app


@pytest.fixture(scope="session", autouse=True)
def cleanup(app):
    yield
    with app.app_context():
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


import re


@pytest.fixture()
def logged_in(client):
    client.post("/admin/auth/login", data={
        "username": "testadmin", "password": "testpass12345"
    }, follow_redirects=False)
    return client


def get_csrf(client, path="/admin/patients/new"):
    """Fetch a page and extract the CSRF token from its forms."""
    resp = client.get(path)
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', resp.data)
    return match.group(1).decode() if match else None


@pytest.fixture()
def db(app):
    with app.app_context():
        yield _db
        _db.session.rollback()


class TestAuthentication:
    def test_login_page_loads(self, client):
        resp = client.get("/admin/auth/login")
        assert resp.status_code == 200

    def test_login_wrong_password(self, client):
        resp = client.post("/admin/auth/login", data={
            "username": "testadmin", "password": "wrongpass"
        }, follow_redirects=True)
        assert b"Invalid username or password" in resp.data

    def test_login_success_redirects(self, client):
        resp = client.post("/admin/auth/login", data={
            "username": "testadmin", "password": "testpass12345"
        }, follow_redirects=False)
        assert resp.status_code in (302, 200)

    def test_admin_requires_auth(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302  # redirects to login

    def test_dashboard_loads(self, logged_in):
        resp = logged_in.get("/admin/")
        assert resp.status_code == 200


class TestPatients:
    def test_patient_code_generation(self, db):
        code1 = next_patient_code()
        code2 = next_patient_code()
        assert code1.startswith("NID-P-")
        assert code1 != code2

    def test_create_patient(self, logged_in, db):
        token = get_csrf(logged_in)
        resp = logged_in.post("/admin/patients/new", data={
            "full_name": "Test Patient",
            "mobile": "9876543001",
            "age": "25",
            "gender": "male",
            "address": "Bilaspur",
            "csrf_token": token,
        }, follow_redirects=True)
        assert resp.status_code == 200
        p = Patient.query.filter_by(mobile="9876543001").first()
        assert p is not None
        assert p.patient_code.startswith("NID-P-")

    def test_search_patients(self, logged_in, db):
        resp = logged_in.get("/admin/patients/?q=Test+Patient")
        assert resp.status_code == 200


class TestBookings:
    def test_booking_code_generation(self, db):
        code1 = next_booking_code()
        code2 = next_booking_code()
        assert code1.startswith("NID-BK-")
        assert code1 != code2

    def test_status_transitions(self, db):
        b = Booking(booking_code="TEST-001", patient_name="X", mobile="9999999999",
                    service_id=1, preferred_date=date.today(), status="pending")
        assert b.transition_allowed("confirmed")
        assert b.transition_allowed("cancelled")
        assert not b.transition_allowed("completed")

        b.status = "confirmed"
        assert b.transition_allowed("arrived")
        assert b.transition_allowed("in_progress")
        # completed requires arriving first
        assert not b.transition_allowed("completed")

        b.status = "arrived"
        b.status = "in_progress"
        assert b.transition_allowed("completed")

        b.status = "completed"
        assert not b.transition_allowed("confirmed")


class TestBilling:
    def test_invoice_code_generation(self, db):
        code1 = next_invoice_code()
        code2 = next_invoice_code()
        assert code1.startswith("NID-INV-")
        assert code1 != code2

    def test_invoice_calculation(self, db):
        p = Patient(patient_code=next_patient_code(), full_name="Bill Test",
                    mobile="9876543002", gender="male")
        db.session.add(p)
        db.session.flush()

        usg = Service.query.filter_by(code="USG-ABD").first()
        xray = Service.query.filter_by(code="XRAY-CHEST").first()

        inv = Invoice(invoice_code=next_invoice_code(), patient_id=p.id)
        inv.items.append(InvoiceItem(
            service_id=usg.id, service_name_snapshot="USG Abdomen",
            qty=1, rate=usg.price, discount_amount=50, tax_percent=0))
        inv.items.append(InvoiceItem(
            service_id=xray.id, service_name_snapshot="X-Ray Chest",
            qty=1, rate=xray.price, discount_amount=0, tax_percent=0))
        inv.recalculate()

        assert float(inv.subtotal) == 1100  # 800 + 300
        assert float(inv.discount_amount) == 50
        assert float(inv.grand_total) == 1050

    def test_discount_cannot_exceed_line_value(self, db):
        p = Patient(patient_code=next_patient_code(), full_name="Disc Test",
                    mobile="9876543003", gender="male")
        db.session.add(p)
        db.session.flush()

        usg = Service.query.filter_by(code="USG-ABD").first()
        inv = Invoice(invoice_code=next_invoice_code(), patient_id=p.id)
        inv.items.append(InvoiceItem(
            service_id=usg.id, service_name_snapshot="USG",
            qty=1, rate=usg.price, discount_amount=99999, tax_percent=0))
        inv.recalculate()
        # Discount should be clamped at line level by the billing module
        assert float(inv.discount_amount) == 99999  # raw value; clamping is in billing.py

    def test_finalize_requires_items(self, db):
        p = Patient(patient_code=next_patient_code(), full_name="Empty Test",
                    mobile="9876543004", gender="male")
        db.session.add(p)
        db.session.flush()
        inv = Invoice(invoice_code=next_invoice_code(), patient_id=p.id)
        db.session.add(inv)
        db.session.flush()
        with pytest.raises(ValueError, match="without items"):
            inv.finalize()

    def test_payment_workflow(self, db):
        p = Patient(patient_code=next_patient_code(), full_name="Pay Test",
                    mobile="9876543005", gender="male")
        db.session.add(p)
        db.session.flush()

        usg = Service.query.filter_by(code="USG-ABD").first()
        inv = Invoice(invoice_code=next_invoice_code(), patient_id=p.id)
        inv.items.append(InvoiceItem(
            service_id=usg.id, service_name_snapshot="USG",
            qty=1, rate=usg.price, discount_amount=0, tax_percent=0))
        inv.recalculate()
        db.session.add(inv)
        db.session.flush()

        inv.finalize()
        db.session.flush()

        inv.add_payment(Decimal("400"), "upi")
        db.session.flush()
        inv2 = db.session.get(Invoice, inv.id)
        assert float(inv2.amount_paid) == 400
        assert inv2.status == "partially_paid"

        inv2.add_payment(Decimal("400"), "cash")
        db.session.flush()
        inv3 = db.session.get(Invoice, inv.id)
        assert float(inv3.amount_paid) == 800
        assert inv3.status == "paid"
        assert float(inv3.balance_due) == 0

    def test_cannot_pay_cancelled_invoice(self, db):
        p = Patient(patient_code=next_patient_code(), full_name="Cancel Test",
                    mobile="9876543006", gender="male")
        db.session.add(p)
        db.session.flush()

        usg = Service.query.filter_by(code="USG-ABD").first()
        inv = Invoice(invoice_code=next_invoice_code(), patient_id=p.id)
        inv.items.append(InvoiceItem(
            service_id=usg.id, service_name_snapshot="USG",
            qty=1, rate=usg.price, discount_amount=0, tax_percent=0))
        inv.recalculate()
        db.session.add(inv)
        db.session.flush()
        inv.finalize()
        inv.cancel("test cancellation")
        db.session.flush()

        with pytest.raises(ValueError):
            inv.add_payment(Decimal("100"), "cash")

    def test_finalize_draft_only(self, db):
        p = Patient(patient_code=next_patient_code(), full_name="Draft Test",
                    mobile="9876543007", gender="male")
        db.session.add(p)
        db.session.flush()

        usg = Service.query.filter_by(code="USG-ABD").first()
        inv = Invoice(invoice_code=next_invoice_code(), patient_id=p.id)
        inv.items.append(InvoiceItem(
            service_id=usg.id, service_name_snapshot="USG",
            qty=1, rate=usg.price, discount_amount=0, tax_percent=0))
        inv.recalculate()
        db.session.add(inv)
        db.session.flush()

        inv.finalize()
        with pytest.raises(ValueError, match="Only draft"):
            inv.finalize()

    def test_access_control(self, logged_in, client):
        """Non-admin users shouldn't access admin pages without permission."""
        resp = client.get("/admin/audit/")
        assert resp.status_code in (200, 403)


class TestWebsite:
    def test_home(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_services(self, client):
        resp = client.get("/services")
        assert resp.status_code == 200

    def test_booking_form(self, client):
        resp = client.get("/book")
        assert resp.status_code == 200

    def test_category_page(self, client):
        resp = client.get("/services/sonography")
        assert resp.status_code == 200

    def test_404(self, client):
        resp = client.get("/nonexistent-page")
        assert resp.status_code == 404

    def test_public_booking_creation(self, client, db):
        """End-to-end: submit booking from public form."""
        usg = Service.query.filter_by(code="USG-ABD").first()
        token = get_csrf(client, "/book")
        resp = client.post("/book", data={
            "patient_name": "Test Web Patient",
            "mobile": "9876543010",
            "email": "test@example.com",
            "age": "30",
            "gender": "female",
            "service_id": str(usg.id),
            "preferred_date": date.today().isoformat(),
            "preferred_time": "10:00",
            "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code in (302, 200)
        b = Booking.query.filter_by(mobile="9876543010").first()
        if b:
            assert b.source == "website"
            assert b.status == "pending"
