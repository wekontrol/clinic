import os
from datetime import date, datetime
from flask import render_template, redirect, url_for, send_from_directory, current_app, abort
from flask_login import login_required, current_user

from . import main_bp
from ..models import Role, User, Patient, Treatment, Medicine, Room, Appointment, ClinicalSession, AuditLog
from ..extensions import db


@main_bp.route('/uploads/<path:filename>')
@login_required
def serve_upload(filename):
    """Serve files from the uploads folder with object-level authorization."""
    upload_folder = current_app.config['UPLOAD_FOLDER']
    # Prevent path traversal
    safe_path = os.path.normpath(filename)
    if safe_path.startswith('..') or safe_path.startswith('/'):
        abort(404)

    # Signatures are accessible to the owner + clinical staff
    if safe_path.startswith('signatures/'):
        # Anyone can serve their own signature; clinical staff can view any
        if current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST, Role.RECEPTION]:
            return send_from_directory(upload_folder, safe_path)
        # Patients may only see their dentist's signature (via PDF, not direct URL)
        abort(403)

    # Object-level auth
    if current_user.role == Role.PATIENT:
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        if patient:
            # Allow own profile photo
            if safe_path == patient.photo_path:
                pass
            # Allow evolution photos belonging to them
            elif safe_path.startswith(f'evolution/{patient.id}/'):
                pass
            # Allow xrays from their own sessions
            elif safe_path.startswith('xrays/'):
                from ..models import XRay
                xray = XRay.query.filter_by(file_path=safe_path).first()
                if not xray:
                    abort(403)
                from ..models import ClinicalSession
                sess = ClinicalSession.query.get(xray.session_id)
                if not sess or sess.patient_id != patient.id:
                    abort(403)
            else:
                abort(403)
        else:
            abort(403)
    elif current_user.role == Role.DENTIST:
        # Dentists may only access files belonging to their assigned patients
        if safe_path.startswith('photos/'):
            allowed = Patient.query.filter_by(
                assigned_dentist_id=current_user.id,
                photo_path=safe_path
            ).first()
            if not allowed:
                abort(403)
        elif safe_path.startswith('evolution/'):
            # evolution/<patient_id>/...
            parts = safe_path.split('/')
            if len(parts) >= 2:
                try:
                    pid = int(parts[1])
                    pat = Patient.query.get(pid)
                    if not pat or pat.assigned_dentist_id != current_user.id:
                        abort(403)
                except ValueError:
                    abort(403)
        elif safe_path.startswith('xrays/'):
            from ..models import XRay, ClinicalSession
            xray = XRay.query.filter_by(file_path=safe_path).first()
            if not xray:
                abort(403)
            sess = ClinicalSession.query.get(xray.session_id)
            if not sess or sess.dentist_id != current_user.id:
                abort(403)

    return send_from_directory(upload_folder, safe_path)


@main_bp.route('/')
def index():
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    ctx = {}

    if current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        ctx['total_patients'] = Patient.query.filter_by(is_active=True).count()
        ctx['total_sessions'] = ClinicalSession.query.count()
        ctx['total_dentists'] = User.query.filter_by(role=Role.DENTIST, is_active=True).count()

        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end   = datetime.combine(date.today(), datetime.max.time())
        ctx['total_appointments_today'] = (Appointment.query
            .filter(Appointment.start_time >= today_start,
                    Appointment.start_time <= today_end)
            .count())

        ctx['recent_sessions'] = (ClinicalSession.query
                                   .order_by(ClinicalSession.created_at.desc())
                                   .limit(5).all())
        ctx['rooms'] = Room.query.order_by(Room.number).all()

        if not ctx['rooms']:
            _seed_rooms()
            ctx['rooms'] = Room.query.order_by(Room.number).all()

        ctx['recent_audits'] = (AuditLog.query
                                 .order_by(AuditLog.timestamp.desc())
                                 .limit(8).all())

    elif current_user.role == Role.DENTIST:
        ctx['my_patients'] = (Patient.query
                               .filter_by(assigned_dentist_id=current_user.id, is_active=True)
                               .count())
        ctx['my_sessions'] = (ClinicalSession.query
                               .filter_by(dentist_id=current_user.id)
                               .count())
        ctx['recent_sessions'] = (ClinicalSession.query
                                   .filter_by(dentist_id=current_user.id)
                                   .order_by(ClinicalSession.created_at.desc())
                                   .limit(5).all())
        ctx['rooms'] = Room.query.order_by(Room.number).all()
        if not ctx['rooms']:
            _seed_rooms()
            ctx['rooms'] = Room.query.order_by(Room.number).all()

    elif current_user.role == Role.RECEPTION:
        ctx['rooms'] = Room.query.order_by(Room.number).all()
        if not ctx['rooms']:
            _seed_rooms()
            ctx['rooms'] = Room.query.order_by(Room.number).all()
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = datetime.combine(date.today(), datetime.max.time())
        ctx['total_appointments_today'] = (Appointment.query
            .filter(Appointment.start_time >= today_start,
                    Appointment.start_time <= today_end)
            .count())

    elif current_user.role == Role.PATIENT:
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        ctx['patient'] = patient
        if patient:
            ctx['sessions'] = (ClinicalSession.query
                                .filter_by(patient_id=patient.id)
                                .order_by(ClinicalSession.session_date.desc())
                                .all())

    return render_template('main/dashboard.html', **ctx)


@main_bp.route('/patient/downloads')
@login_required
def patient_downloads():
    from ..models import Patient, ClinicalSession, Prescription
    if current_user.role != Role.PATIENT:
        abort(403)
    patient = Patient.query.filter_by(user_id=current_user.id).first_or_404()
    sessions = (ClinicalSession.query
                .filter_by(patient_id=patient.id)
                .order_by(ClinicalSession.session_date.desc())
                .all())
    return render_template('main/patient_downloads.html', patient=patient, sessions=sessions)


def _seed_rooms():
    from ..extensions import db
    from ..models import Room, RoomStatus
    if Room.query.count() == 0:
        r1 = Room(name='Sala de Consulta 1', number=1, status=RoomStatus.GREEN)
        r2 = Room(name='Sala de Consulta 2', number=2, status=RoomStatus.GREEN)
        db.session.add_all([r1, r2])
        db.session.commit()
