import logging
from datetime import datetime, timezone
from flask import request
from flask_login import current_user

logger = logging.getLogger(__name__)


def log_action(table_name, action, record_id=None, old_value=None, new_value=None, description=None):
    from .extensions import db
    from .models import AuditLog

    entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        username=current_user.username if current_user.is_authenticated else 'system',
        action=action.upper(),
        table_name=table_name,
        record_id=record_id,
        old_value=old_value,
        new_value=new_value,
        description=description,
        ip_address=request.remote_addr if request else None,
        timestamp=datetime.now(timezone.utc)
    )
    try:
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error('Audit log write failed for action=%s table=%s record=%s: %s',
                     action, table_name, record_id, exc)
        raise
