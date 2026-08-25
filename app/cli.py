"""CLI: flask init-db / seed / create-admin."""
import click
from datetime import date
from decimal import Decimal

from app.extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (use migrations in production)."""
        with app.app_context():
            db.create_all()
            click.echo("Database tables created.")

    @app.cli.command("seed")
    def seed():
        """Seed roles/permissions, default settings and example services."""
        from app.cli_seed import run_seed

        with app.app_context():
            created = run_seed()
            db.session.commit()
            click.echo(f"Seed complete: {created}")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("email")
    @click.password_option(prompt="Password (min 8 chars): ")
    @click.option("--name", default="Administrator", show_default=True)
    def create_admin(username, email, password, name):
        """Create a super admin user: flask create-admin <user> <email>"""
        from app.models.user import User, Role

        with app.app_context():
            role = Role.query.filter_by(name="super_admin").first()
            if role is None:
                raise click.ClickException("Run `flask seed` first.")
            if User.query.filter(
                (User.username == username) | (User.email == email)
            ).first():
                raise click.ClickException("Username or email already exists.")
            user = User(username=username, email=email, full_name=name,
                        role_id=role.id, is_active=True)
            try:
                user.set_password(password)
            except ValueError as exc:
                raise click.ClickException(str(exc))
            db.session.add(user)
            db.session.commit()
            click.echo(f"Super admin '{username}' created.")

    @app.cli.command("seed-demo")
    @click.confirmation_option(prompt="Insert DEMO patients/bookings/invoices? ")
    def seed_demo():
        """Optional demo data for development/testing only."""
        from app.cli_seed import seed_demo_data

        with app.app_context():
            summary = seed_demo_data()
            db.session.commit()
            click.echo(f"Demo data inserted: {summary}")
