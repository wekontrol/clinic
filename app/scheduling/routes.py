import json
from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from flask_babel import gettext as _

from . import scheduling_bp
from .forms import AppointmentForm, EmergencyForm, RoomStatusForm
from ..models import Appointment, Patient, User, Room, Role, RoomStatus, ClinicalSession
from ..extensions import db
from ..audit import log_action


def _scheduling_roles():
    return [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.RECEPTION]


def _check_scheduling_access():
    if current_user.role not in _scheduling_roles():
        abort(403)


def _get_patient_choices():
    patients = Patient.query.filter_by(is_active=True).order_by(Patient.full_name).all()
    return [(0, '---')] + [(p.id, p.full_name) for p in patients]


def _get_dentist_choices():
    dentists = User.query.filter(
        User.role.in_([Role.DENTIST, Role.CLINICAL_DIRECTOR]),
        User.is_active == True
    ).order_by(User.full_name).all()
    return [(0, '---')] + [(d.id, d.full_name) for d in dentists]


def _get_room_choices():
    rooms = Room.query.order_by(Room.number).all()
    return [(0, '---')] + [(r.id, f'{_("Sala")} {r.number} — {r.name}') for r in rooms]


# ─── CALENDAR PAGE ────────────────────────────────────────────────────────────

@scheduling_bp.route('/')
@login_required
def calendar():
    _check_scheduling_access()
    rooms = Room.query.order_by(Room.number).all()
    dentists = User.query.filter(
        User.role.in_([Role.DENTIST, Role.CLINICAL_DIRECTOR]),
        User.is_active == True
    ).all()
    patients = Patient.query.filter_by(is_active=True).order_by(Patient.full_name).all()
    return render_template('scheduling/calendar.html', rooms=rooms, dentists=dentists,
                           patients=patients)


# ─── APPOINTMENTS JSON API ────────────────────────────────────────────────────

@scheduling_bp.route('/appointments/api')
@login_required
def appointments_api():
    _check_scheduling_access()
    start_str = request.args.get('start')
    end_str   = request.args.get('end')
    query = Appointment.query

    def _parse_naive(s):
        """Parse ISO datetime string → naive datetime for comparison with DB naive values."""
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return dt.replace(tzinfo=None)  # strip timezone so SQLite comparison works
        except (ValueError, AttributeError):
            return None

    if start_str:
        dt = _parse_naive(start_str)
        if dt:
            query = query.filter(Appointment.start_time >= dt)
    if end_str:
        dt = _parse_naive(end_str)
        if dt:
            query = query.filter(Appointment.start_time <= dt)

    appointments = query.order_by(Appointment.start_time).all()

    room_colors = ['#14b8a6', '#22c55e', '#f59e0b', '#a78bfa', '#06b6d4']

    events = []
    for appt in appointments:
        if not appt.start_time:
            continue
        room_num = appt.room.number if appt.room else 0
        if appt.is_emergency:
            color = '#f85149'
        else:
            color = room_colors[(room_num - 1) % len(room_colors)] if room_num else '#58a6ff'

        dentist_name = appt.dentist.full_name if appt.dentist else '?'
        patient_name = appt.patient.full_name if appt.patient else '?'
        title = f'{patient_name} – {dentist_name}'

        events.append({
            'id': str(appt.id),
            'title': title,
            'start': appt.start_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'end':   appt.end_time.strftime('%Y-%m-%dT%H:%M:%S') if appt.end_time else None,
            'color': color,
            'borderColor': color,
            'textColor': '#ffffff',
            'extendedProps': {
                'patient':      patient_name,
                'dentist':      dentist_name,
                'room':         f'{_("Sala")} {room_num}' if room_num else '',
                'notes':        appt.notes or '',
                'is_emergency': appt.is_emergency,
                'status':       appt.status,
                'appt_id':      appt.id,
            }
        })

    return jsonify(events)


# ─── APPOINTMENT CRUD ─────────────────────────────────────────────────────────

@scheduling_bp.route('/appointments/new', methods=['GET', 'POST'])
@login_required
def new_appointment():
    _check_scheduling_access()
    form = AppointmentForm()
    form.patient_id.choices = _get_patient_choices()
    form.dentist_id.choices = _get_dentist_choices()
    form.room_id.choices = _get_room_choices()

    if form.validate_on_submit():
        appt = Appointment(
            patient_id=form.patient_id.data,
            dentist_id=form.dentist_id.data,
            room_id=form.room_id.data or None,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            notes=form.notes.data or None,
            is_emergency=form.is_emergency.data,
            status='scheduled',
            created_by_id=current_user.id,
        )
        db.session.add(appt)
        db.session.commit()
        log_action('appointments', 'CREATE', record_id=appt.id,
                   description=f'Appointment created for patient_id={appt.patient_id}')
        flash(_('Consulta agendada com sucesso!'), 'success')
        return redirect(url_for('scheduling.calendar'))

    # Pre-fill from query string (e.g. quick-add from calendar click)
    if request.method == 'GET':
        start_str = request.args.get('start')
        if start_str:
            try:
                form.start_time.data = datetime.fromisoformat(start_str)
                form.end_time.data = form.start_time.data + timedelta(minutes=30)
            except ValueError:
                pass

    patients = Patient.query.filter_by(is_active=True).order_by(Patient.full_name).all()
    return render_template('scheduling/appointment_form.html', form=form, appt=None,
                           patients=patients, title=_('Nova Consulta'))


@scheduling_bp.route('/appointments/<int:appt_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_appointment(appt_id):
    _check_scheduling_access()
    appt = Appointment.query.get_or_404(appt_id)
    form = AppointmentForm(obj=appt)
    form.patient_id.choices = _get_patient_choices()
    form.dentist_id.choices = _get_dentist_choices()
    form.room_id.choices = _get_room_choices()

    if form.validate_on_submit():
        appt.patient_id = form.patient_id.data
        appt.dentist_id = form.dentist_id.data
        appt.room_id = form.room_id.data or None
        appt.start_time = form.start_time.data
        appt.end_time = form.end_time.data
        appt.notes = form.notes.data or None
        appt.is_emergency = form.is_emergency.data
        db.session.commit()
        log_action('appointments', 'UPDATE', record_id=appt.id,
                   description='Appointment updated')
        flash(_('Consulta atualizada com sucesso!'), 'success')
        return redirect(url_for('scheduling.calendar'))

    patients = Patient.query.filter_by(is_active=True).order_by(Patient.full_name).all()
    return render_template('scheduling/appointment_form.html', form=form, appt=appt,
                           patients=patients, title=_('Editar Consulta'))


@scheduling_bp.route('/appointments/<int:appt_id>/delete', methods=['POST'])
@login_required
def delete_appointment(appt_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.RECEPTION]:
        abort(403)
    appt = Appointment.query.get_or_404(appt_id)
    db.session.delete(appt)
    db.session.commit()
    log_action('appointments', 'DELETE', record_id=appt_id,
               description='Appointment deleted')
    flash(_('Consulta cancelada.'), 'info')
    return redirect(url_for('scheduling.calendar'))


# ─── APPOINTMENT DETAIL API (for modal) ───────────────────────────────────────

@scheduling_bp.route('/appointments/<int:appt_id>/detail')
@login_required
def appointment_detail(appt_id):
    _check_scheduling_access()
    appt = Appointment.query.get_or_404(appt_id)
    existing_session = ClinicalSession.query.filter_by(appointment_id=appt.id).first()
    can_start = current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR,
                                       Role.DENTIST]
    return jsonify({
        'id': appt.id,
        'patient': appt.patient.full_name,
        'patient_id': appt.patient_id,
        'dentist': appt.dentist.full_name if appt.dentist else '',
        'dentist_id': appt.dentist_id,
        'room': f'{appt.room.number}' if appt.room else '',
        'room_id': appt.room_id,
        'start': appt.start_time.strftime('%Y-%m-%dT%H:%M') if appt.start_time else '',
        'end': appt.end_time.strftime('%Y-%m-%dT%H:%M') if appt.end_time else '',
        'notes': appt.notes or '',
        'is_emergency': appt.is_emergency,
        'status': appt.status,
        'edit_url': url_for('scheduling.edit_appointment', appt_id=appt.id),
        'delete_url': url_for('scheduling.delete_appointment', appt_id=appt.id),
        'start_session_url': url_for('sessions.start_from_appointment', appointment_id=appt.id) if can_start else None,
        'existing_session_url': url_for('sessions.edit', session_id=existing_session.id) if existing_session else None,
        'session_code': existing_session.session_code if existing_session else None,
    })


# ─── ROOM STATUS ──────────────────────────────────────────────────────────────

@scheduling_bp.route('/rooms')
@login_required
def rooms():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR,
                                  Role.RECEPTION, Role.DENTIST]:
        abort(403)
    rooms = Room.query.order_by(Room.number).all()
    form = RoomStatusForm()
    return render_template('scheduling/rooms.html', rooms=rooms, form=form)


@scheduling_bp.route('/rooms/<int:room_id>/status', methods=['POST'])
@login_required
def update_room_status(room_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR,
                                  Role.RECEPTION, Role.DENTIST]:
        abort(403)
    form = RoomStatusForm()
    if form.validate_on_submit():
        room = Room.query.get_or_404(room_id)
        new_status = form.status.data

        # Dentists may only toggle their own room between green/yellow (not emergency).
        # They are considered to "own" a room if they have an appointment there today.
        if current_user.role == Role.DENTIST:
            if new_status == 'red':
                flash(_('Dentistas não podem definir o estado de Emergência. Contacte a Recepção.'), 'warning')
                return redirect(request.referrer or url_for('scheduling.rooms'))
            # Check dentist has an appointment in this room
            from datetime import date
            today = date.today()
            has_appt = Appointment.query.filter(
                Appointment.dentist_id == current_user.id,
                Appointment.room_id == room_id,
                db.func.date(Appointment.start_time) == today
            ).first()
            if not has_appt:
                flash(_('Apenas pode atualizar o estado de salas com consultas agendadas para hoje.'), 'warning')
                return redirect(request.referrer or url_for('scheduling.rooms'))

        old_status = room.status
        room.status = new_status
        room.status_note = form.status_note.data or None
        room.status_updated_by_id = current_user.id
        room.status_updated_at = datetime.now(timezone.utc)
        db.session.commit()
        log_action('rooms', 'UPDATE', record_id=room_id,
                   old_value=old_status, new_value=new_status,
                   description=f'Room {room.number} status changed')
        flash(_('Estado da Sala %(num)s atualizado.', num=room.number), 'success')
    return redirect(request.referrer or url_for('scheduling.rooms'))


# ─── EMERGENCY PROTOCOL ───────────────────────────────────────────────────────

@scheduling_bp.route('/emergency', methods=['GET', 'POST'])
@login_required
def emergency():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR,
                                  Role.RECEPTION, Role.DENTIST]:
        abort(403)
    form = EmergencyForm()
    active_patients = Patient.query.filter_by(is_active=True).order_by(Patient.full_name).all()
    form.patient_id.choices = [(0, '--- ' + _('Novo Paciente') + ' ---')] + [
        (p.id, p.full_name) for p in active_patients
    ]
    form.dentist_id.choices = [(0, '---')] + [
        (d.id, d.full_name)
        for d in User.query.filter(
            User.role.in_([Role.DENTIST, Role.CLINICAL_DIRECTOR]),
            User.is_active == True
        ).all()
    ]
    form.room_id.choices = [
        (r.id, f'{_("Sala")} {r.number} — {r.name}')
        for r in Room.query.order_by(Room.number).all()
    ]

    if form.validate_on_submit():
        patient_id = form.patient_id.data or None
        patient_name = (form.patient_name.data or '').strip()

        # Require either an existing patient or a name for a new one
        if not patient_id and not patient_name:
            form.patient_name.errors.append(
                _('Indique o nome do paciente ou selecione um paciente existente.')
            )
            return render_template('scheduling/emergency.html', form=form, patients=active_patients)

        if not patient_id:
            if not patient_name:
                form.patient_name.errors.append(_('Nome do paciente é obrigatório.'))
                return render_template('scheduling/emergency.html', form=form, patients=active_patients)
            emergency_patient = Patient(
                full_name=patient_name,
                is_active=True,
            )
            db.session.add(emergency_patient)
            db.session.flush()
            patient_id = emergency_patient.id
            log_action('patients', 'CREATE', record_id=patient_id,
                       description=f'Emergency patient created: {patient_name}')

        room = Room.query.get(form.room_id.data)
        if room:
            room.status = RoomStatus.RED
            room.status_note = _('URGÊNCIA')
            room.status_updated_by_id = current_user.id
            room.status_updated_at = datetime.now(timezone.utc)

        now = datetime.now()
        appt = Appointment(
            patient_id=patient_id,
            dentist_id=form.dentist_id.data,
            room_id=form.room_id.data,
            start_time=now,
            end_time=now + timedelta(hours=1),
            notes=form.notes.data or _('URGÊNCIA'),
            is_emergency=True,
            status='scheduled',
            created_by_id=current_user.id,
        )
        db.session.add(appt)
        db.session.commit()
        log_action('appointments', 'CREATE', record_id=appt.id,
                   description=f'EMERGENCY appointment for patient_id={patient_id}')
        flash(_('Urgência registada! Sala definida como Emergência.'), 'danger')
        return redirect(url_for('scheduling.calendar'))

    return render_template('scheduling/emergency.html', form=form, patients=active_patients)
