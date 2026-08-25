"""Admin audit log viewer."""
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models.audit import AuditLog
from app.utils.helpers import permission_required

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/")
@login_required
@permission_required("audit.view")
def index():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    action = request.args.get("action") or ""

    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            AuditLog.action.ilike(like),
            AuditLog.entity_type.ilike(like),
            AuditLog.entity_id.ilike(like),
        ))
    pagination = query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=30)
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    return render_template("admin/audit/index.html", pagination=pagination,
                           q=q, action=action, actions=actions)
