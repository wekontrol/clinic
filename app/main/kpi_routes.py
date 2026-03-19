"""Chart.js KPI API routes for Clinical Director / Superadmin dashboard."""
import json
from datetime import datetime, timedelta
from functools import wraps

from flask import Response
from flask_login import current_user

from . import main_bp
from ..models import Role, Appointment, ClinicalSession, SessionTreatment, Patient, User, Room, Treatment
from ..extensions import db
from sqlalchemy import func


_MONTH_NAMES = {
    '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
    '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
    '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
}


def _fmt_month(ym: str) -> str:
    """'2026-03' → 'Mar 2026'"""
    try:
        y, m = ym.split('-')
        return f"{_MONTH_NAMES.get(m, m)} {y}"
    except Exception:
        return ym


def _fmt_week(yw: str) -> str:
    """'2026-W11' → 'Sem 11/26'"""
    try:
        parts = yw.split('-W')
        return f"Sem {int(parts[1])}/{parts[0][2:]}"
    except Exception:
        return yw


def _json(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False),
                    status=status, mimetype='application/json')


def _director_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return _json({'error': 'unauthorized', 'labels': [], 'data': []}, 401)
        if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
            return _json({'error': 'forbidden', 'labels': [], 'data': []}, 403)
        return f(*args, **kwargs)
    return decorated


def _naive_cutoff(days=0, weeks=0):
    """Return a naive UTC datetime N days/weeks ago."""
    return datetime.utcnow() - timedelta(days=days, weeks=weeks)


@main_bp.route('/kpi/appointments-per-week')
@_director_required
def kpi_appointments_per_week():
    cutoff = _naive_cutoff(weeks=12)
    rows = (db.session.query(
                func.strftime('%Y-W%W', Appointment.start_time).label('week'),
                func.count(Appointment.id).label('cnt')
            )
            .filter(Appointment.start_time >= cutoff)
            .group_by('week')
            .order_by('week')
            .all())
    labels = [_fmt_week(r.week) for r in rows]
    data   = [r.cnt for r in rows]
    if not labels:
        total = Appointment.query.count()
        labels = ['Total']
        data   = [total]
    return _json({'labels': labels, 'data': data})


@main_bp.route('/kpi/appointments-per-month')
@_director_required
def kpi_appointments_per_month():
    cutoff = _naive_cutoff(days=365)
    rows = (db.session.query(
                func.strftime('%Y-%m', Appointment.start_time).label('month'),
                func.count(Appointment.id).label('cnt')
            )
            .filter(Appointment.start_time >= cutoff)
            .group_by('month')
            .order_by('month')
            .all())
    labels = [_fmt_month(r.month) for r in rows]
    data   = [r.cnt for r in rows]
    if not labels:
        total = Appointment.query.count()
        labels = ['Total']
        data   = [total]
    return _json({'labels': labels, 'data': data})


@main_bp.route('/kpi/top-treatments')
@_director_required
def kpi_top_treatments():
    rows = (db.session.query(
                SessionTreatment.treatment_id,
                func.count(SessionTreatment.id).label('cnt')
            )
            .group_by(SessionTreatment.treatment_id)
            .order_by(func.count(SessionTreatment.id).desc())
            .limit(8)
            .all())
    labels, data = [], []
    for r in rows:
        t = db.session.get(Treatment, r.treatment_id)
        if t:
            labels.append(t.name_pt or t.name_en or str(r.treatment_id))
            data.append(r.cnt)

    if not labels:
        tx_rows = (db.session.query(Treatment.name_pt, Treatment.id)
                   .order_by(Treatment.name_pt).limit(8).all())
        if tx_rows:
            labels = [r.name_pt for r in tx_rows]
            data   = [0] * len(labels)
        else:
            labels = ['Sem dados']
            data   = [0]
    return _json({'labels': labels, 'data': data})


@main_bp.route('/kpi/patients-by-doctor')
@_director_required
def kpi_patients_by_doctor():
    dentists = User.query.filter_by(role=Role.DENTIST, is_active=True).all()
    labels = []
    data   = []
    for u in dentists:
        cnt = Patient.query.filter_by(assigned_dentist_id=u.id, is_active=True).count()
        name = u.full_name.replace('Dr. ', '').replace('Dra. ', '').strip()
        labels.append(name)
        data.append(cnt)
    if not labels:
        labels = ['Sem dentistas']
        data   = [0]
    return _json({'labels': labels, 'data': data})


@main_bp.route('/kpi/sessions-per-month')
@_director_required
def kpi_sessions_per_month():
    cutoff = _naive_cutoff(days=180)
    rows = (db.session.query(
                func.strftime('%Y-%m', ClinicalSession.session_date).label('month'),
                func.count(ClinicalSession.id).label('cnt')
            )
            .filter(ClinicalSession.session_date >= cutoff)
            .group_by('month')
            .order_by('month')
            .all())
    labels = [_fmt_month(r.month) for r in rows]
    data   = [r.cnt for r in rows]
    if not labels:
        total = ClinicalSession.query.count()
        labels = ['Total']
        data   = [total]
    return _json({'labels': labels, 'data': data})


@main_bp.route('/kpi/room-utilization')
@_director_required
def kpi_room_utilization():
    rooms = Room.query.order_by(Room.number).all()
    labels, data = [], []
    for room in rooms:
        cnt = Appointment.query.filter_by(room_id=room.id).count()
        labels.append(room.name.replace('Sala de Consulta', 'Sala'))
        data.append(cnt)
    if not labels:
        labels = ['Sem salas']
        data   = [0]
    return _json({'labels': labels, 'data': data})


@main_bp.route('/kpi/new-patients-per-month')
@_director_required
def kpi_new_patients_per_month():
    cutoff = _naive_cutoff(days=365)
    rows = (db.session.query(
                func.strftime('%Y-%m', Patient.created_at).label('month'),
                func.count(Patient.id).label('cnt')
            )
            .filter(Patient.created_at >= cutoff)
            .group_by('month')
            .order_by('month')
            .all())
    labels = [_fmt_month(r.month) for r in rows]
    data   = [r.cnt for r in rows]
    if not labels:
        labels = ['Total']
        data   = [Patient.query.count()]
    return _json({'labels': labels, 'data': data})
