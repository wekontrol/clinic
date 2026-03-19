"""
SQLAlchemy event-based audit hooks for medical traceability.

Registers:
  before_flush — enforce ClinicalSession immutability (ORM-layer safety net).
  after_flush  — capture every INSERT/UPDATE/DELETE on clinical tables with
                 full old/new JSON, actor (user_id + username), timestamp, and IP.

The global after_flush listener guarantees complete coverage even when a code
path lacks an explicit log_action() call. Manual log_action() calls in routes
are NOT removed; they provide semantic context (e.g. "Session closed") while
the listener captures low-level field diffs.

To prevent duplicate rows in the AuditLog table for the SAME operation the
listener uses the session-level `_audit_written` set to de-duplicate by
(table_name, record_id, action) within a single flush.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Tables covered by global listener
AUDITED_TABLES = frozenset({
    'clinical_sessions', 'session_treatments', 'session_addenda',
    'prescriptions', 'xrays', 'evolution_photos',
})


def _model_to_dict(instance):
    """Serialize model to a plain dict with only JSON-safe scalars."""
    d = {}
    for col in instance.__table__.columns:
        val = getattr(instance, col.name, None)
        if val is None:
            d[col.name] = None
        elif isinstance(val, (str, int, float, bool)):
            d[col.name] = val
        else:
            d[col.name] = str(val)
    return d


def _safe_scalar(val):
    """Convert a value to a JSON-safe scalar."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    return str(val)


def _changed_fields(instance):
    """Return (old_dict, new_dict) for columns with pending changes (JSON-safe)."""
    from sqlalchemy.orm import attributes
    old, new = {}, {}
    for col in instance.__table__.columns:
        hist = attributes.get_history(instance, col.name)
        if hist.deleted:
            old[col.name] = _safe_scalar(hist.deleted[0])
            new[col.name] = _safe_scalar(hist.added[0] if hist.added else getattr(instance, col.name, None))
    return old or None, new or None


def _current_user_info():
    try:
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return current_user.id, current_user.username
    except RuntimeError:
        pass
    return None, 'system'


def _ip():
    try:
        from flask import request
        return request.remote_addr
    except RuntimeError:
        return None


def _write_audit(db_session, table_name, action, record_id, old_value, new_value, description=''):
    from .models import AuditLog
    uid, uname = _current_user_info()
    entry = AuditLog(
        user_id=uid,
        username=uname,
        action=action,
        table_name=table_name,
        record_id=record_id,
        old_value=old_value,
        new_value=new_value,
        description=description,
        ip_address=_ip(),
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(entry)


def register_events(db):
    """Call once from create_app() after db.init_app(app)."""
    from sqlalchemy import event

    # ── Immutability guard ────────────────────────────────────────────────────
    @event.listens_for(db.session, 'before_flush')
    def enforce_session_immutability(session, flush_context, instances):
        """ORM-layer safety net: block field changes on ALREADY-CLOSED ClinicalSessions.

        The ONE legal post-open transition is in_progress/scheduled → closed, which
        changes 'status' and 'closed_at'. We allow this by checking the OLD status value
        (hist.deleted[0]). If the OLD status was already CLOSED and any clinical field
        changes, we raise ImmutableSessionError.
        """
        from sqlalchemy.orm import attributes as sa_attrs
        from .models import ClinicalSession, SessionStatus, ImmutableSessionError

        ADMIN_ONLY = {'created_by_id'}
        # Invariant fields: must not change once the session is persisted, at any status
        INVARIANT_FIELDS = {'patient_id', 'dentist_id'}

        for obj in session.dirty:
            if not isinstance(obj, ClinicalSession):
                continue

            # Guard invariant fields (all statuses)
            if obj.id:  # only persisted sessions
                invariant_changed = set()
                for field in INVARIANT_FIELDS:
                    hist = sa_attrs.get_history(obj, field)
                    if hist.deleted:
                        invariant_changed.add(field)
                if invariant_changed:
                    raise ImmutableSessionError(
                        f"Session {obj.session_code}: cannot reassign "
                        f"{', '.join(sorted(invariant_changed))} after creation."
                    )

            # Check the OLD status (before this flush) to know if we were already closed
            status_hist = sa_attrs.get_history(obj, 'status')
            old_status = status_hist.deleted[0] if status_hist.deleted else obj.status
            if old_status != SessionStatus.CLOSED:
                # Not yet closed before this flush — legal to change any field
                continue
            # The session WAS already closed — block all field changes
            changed = set()
            for col in obj.__table__.columns:
                if col.name in ADMIN_ONLY:
                    continue
                hist = sa_attrs.get_history(obj, col.name)
                if hist.deleted:
                    changed.add(col.name)
            if changed:
                raise ImmutableSessionError(
                    f"Session {obj.session_code} is CLOSED and immutable. "
                    f"Cannot modify: {', '.join(sorted(changed))}"
                )

        # Block writes to child clinical records when parent session is ALREADY closed
        from .models import Prescription, XRay, EvolutionPhoto, SessionTreatment
        CHILD_MODELS = (Prescription, XRay, EvolutionPhoto, SessionTreatment)
        for obj in list(session.new) + list(session.dirty) + list(session.deleted):
            if not isinstance(obj, CHILD_MODELS):
                continue
            sess_id = getattr(obj, 'session_id', None)
            if not sess_id:
                continue
            parent = session.get(ClinicalSession, sess_id) or ClinicalSession.query.get(sess_id)
            if parent and parent.status == SessionStatus.CLOSED:
                # Allow if the parent is currently being closed in THIS flush
                # (parent is in session.dirty with status transitioning to CLOSED)
                if parent in session.dirty:
                    status_hist = sa_attrs.get_history(parent, 'status')
                    old_parent_status = status_hist.deleted[0] if status_hist.deleted else parent.status
                    if old_parent_status != SessionStatus.CLOSED:
                        continue  # Legal: parent closing in same flush, child writes are part of close
                raise ImmutableSessionError(
                    f"Session {parent.session_code} is CLOSED. "
                    f"Cannot add/modify/delete {obj.__tablename__} records."
                )

    # ── Global audit capture ──────────────────────────────────────────────────
    @event.listens_for(db.session, 'after_flush')
    def capture_audit(session, flush_context):
        """Write AuditLog rows for INSERT/UPDATE/DELETE on clinical tables."""
        # De-duplicate within same flush to avoid doubling with log_action() calls
        seen = getattr(session, '_audit_seen', set())
        session._audit_seen = seen

        try:
            for obj in list(session.new):
                tbl = getattr(obj, '__tablename__', None)
                if tbl not in AUDITED_TABLES:
                    continue
                pk = getattr(obj, 'id', None)
                key = (tbl, pk, 'CREATE')
                if key in seen:
                    continue
                seen.add(key)
                _write_audit(session, tbl, 'CREATE', pk,
                             old_value=None,
                             new_value=_model_to_dict(obj),
                             description=f'AUTO INSERT {tbl} #{pk}')

            for obj in list(session.dirty):
                tbl = getattr(obj, '__tablename__', None)
                if tbl not in AUDITED_TABLES:
                    continue
                pk = getattr(obj, 'id', None)
                key = (tbl, pk, 'UPDATE')
                if key in seen:
                    continue
                seen.add(key)
                old_val, new_val = _changed_fields(obj)
                if old_val or new_val:
                    _write_audit(session, tbl, 'UPDATE', pk,
                                 old_value=old_val, new_value=new_val,
                                 description=f'AUTO UPDATE {tbl} #{pk}')

            for obj in list(session.deleted):
                tbl = getattr(obj, '__tablename__', None)
                if tbl not in AUDITED_TABLES:
                    continue
                pk = getattr(obj, 'id', None)
                key = (tbl, pk, 'DELETE')
                if key in seen:
                    continue
                seen.add(key)
                _write_audit(session, tbl, 'DELETE', pk,
                             old_value=_model_to_dict(obj),
                             new_value=None,
                             description=f'AUTO DELETE {tbl} #{pk}')

        except Exception as exc:
            logger.error('Audit capture error (non-fatal): %s', exc, exc_info=True)

    @event.listens_for(db.session, 'after_commit')
    def reset_audit_seen(session):
        """Clear the de-duplication set after commit so each transaction is fresh."""
        session._audit_seen = set()
