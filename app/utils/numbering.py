"""Server-side unique document numbering (patients, bookings, invoices).

Uses an atomic UPDATE on a counter table so concurrent requests cannot
allocate the same number. Works identically on SQLite and PostgreSQL.
"""
from datetime import datetime, timezone

from sqlalchemy import update

from app.extensions import db
from app.utils.helpers import get_setting


class Sequence(db.Model):
    __tablename__ = "sequences"

    name = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Integer, nullable=False, default=0)


def _next_value(sequence_name: str) -> int:
    """Atomically increment and return the next counter value."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = db.session.execute(
        update(Sequence)
        .where(Sequence.name == sequence_name)
        .values(value=Sequence.value + 1)
        .returning(Sequence.value)
    )
    row = result.first()
    if row is None:
        db.session.execute(
            Sequence.__table__.insert()
            .values(name=sequence_name, value=1)
        )
        # Upsert race safety: re-read with increment for drivers that
        # already inserted the row concurrently.
        result = db.session.execute(
            update(Sequence)
            .where(Sequence.name == sequence_name)
            .values(value=Sequence.value + 1)
            .returning(Sequence.value)
        )
        row = result.first()
        return int(row[0])
    return int(row[0])


def next_patient_code():
    prefix = get_setting("patient_prefix", "NID-P")
    n = _next_value("patient_code")
    return f"{prefix}-{n:06d}"


def next_booking_code():
    prefix = get_setting("booking_prefix", "NID-BK")
    year = datetime.now().year
    n = _next_value(f"booking_{year}")
    return f"{prefix}-{year}-{n:06d}"


def next_invoice_code():
    prefix = get_setting("invoice_prefix", "NID-INV")
    year = datetime.now().year
    n = _next_value(f"invoice_{year}")
    return f"{prefix}-{year}-{n:06d}"
