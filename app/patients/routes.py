import os
import re
import uuid
import secrets
import string
import unicodedata
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request, abort, current_app, session
from flask_login import login_required, current_user
from flask_babel import gettext as _
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError

from . import patients_bp
from .forms import PatientForm
from ..models import Patient, User, Role, ClinicalSession, PatientCareTeam
from ..extensions import db
from ..decorators import role_required, clinical_staff_required
from ..audit import log_action


def _slug(text):
    """Normalize a name segment: remove accents, keep only [a-z0-9]."""
    nfd = unicodedata.normalize('NFD', text)
    ascii_only = nfd.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', ascii_only.lower())


def _generate_patient_username(full_name, **_kwargs):
    """Generate a unique login username as primeiro.ultimonome."""
    parts = [p for p in full_name.strip().split() if p]
    if len(parts) >= 2:
        first = _slug(parts[0])
        last  = _slug(parts[-1])
        base  = f'{first}.{last}' if first and last else (first or last or 'paciente')
    elif parts:
        base = _slug(parts[0]) or 'paciente'
    else:
        base = 'paciente'
    username = base
    suffix = 1
    while User.query.filter_by(username=username).first():
        username = f'{base}{suffix}'
        suffix += 1
    return username


def _generate_temp_password(length=10):
    alphabet = string.ascii_letters + string.digits + '!@#$'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

ALLOWED_PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}


def _save_photo(file_obj):
    """Save the uploaded photo and return the relative path under uploads/."""
    photos_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'photos')
    os.makedirs(photos_dir, exist_ok=True)
    ext = secure_filename(file_obj.filename).rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        return None
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_obj.save(os.path.join(photos_dir, filename))
    return f"photos/{filename}"


def _dentist_choices():
    dentists = User.query.filter(
        User.role.in_([Role.DENTIST, Role.CLINICAL_DIRECTOR]),
        User.is_active == True
    ).order_by(User.full_name).all()
    choices = [(0, '--- ' + _('Nenhum') + ' ---')]
    choices += [(d.id, d.full_name) for d in dentists]
    return choices


def _patient_query():
    """Return patient query filtered by role."""
    if current_user.role == Role.PATIENT:
        profile = Patient.query.filter_by(user_id=current_user.id, is_active=True).first()
        if profile:
            return Patient.query.filter_by(id=profile.id)
        return Patient.query.filter_by(id=-1)
    elif current_user.role == Role.DENTIST:
        return Patient.query.filter_by(assigned_dentist_id=current_user.id, is_active=True)
    return Patient.query.filter_by(is_active=True)


@patients_bp.route('/')
@login_required
def index():
    if current_user.role == Role.PATIENT:
        profile = Patient.query.filter_by(user_id=current_user.id, is_active=True).first()
        if profile:
            return redirect(url_for('patients.detail', patient_id=profile.id))
        flash(_('O seu perfil de paciente ainda não está associado. Contacte a recepção.'), 'warning')
        return redirect(url_for('main.dashboard'))

    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST, Role.RECEPTION]:
        abort(403)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    query = _patient_query()
    if search:
        query = query.filter(Patient.full_name.ilike(f'%{search}%'))
    query = query.order_by(Patient.full_name)
    patients = query.paginate(page=page, per_page=20)
    return render_template('patients/index.html', patients=patients, search=search)


@patients_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST, Role.RECEPTION]:
        abort(403)
    form = PatientForm()
    form.assigned_dentist_id.choices = _dentist_choices()

    # Pre-select the dentist as their own patient when they open the form
    if request.method == 'GET' and current_user.role == Role.DENTIST:
        form.assigned_dentist_id.data = current_user.id

    if form.validate_on_submit():
        photo_path = None
        if form.photo.data and form.photo.data.filename:
            photo_path = _save_photo(form.photo.data)

        # Dentists can only create patients assigned to themselves
        if current_user.role == Role.DENTIST:
            if not form.assigned_dentist_id.data or form.assigned_dentist_id.data == 0:
                form.assigned_dentist_id.data = current_user.id

        id_doc_val = form.id_doc.data.strip() if form.id_doc.data else None
        if id_doc_val:
            existing = Patient.query.filter(
                Patient.id_doc == id_doc_val
            ).first()
            if existing:
                form.id_doc.errors.append(
                    _('Já existe um paciente com este documento de identificação (%(name)s).',
                      name=existing.full_name)
                )
                return render_template('patients/form.html', form=form, patient=None,
                                       title=_('Novo Paciente'))

        patient = Patient(
            full_name=form.full_name.data,
            date_of_birth=form.date_of_birth.data,
            gender=form.gender.data or None,
            id_doc=id_doc_val,
            nationality=form.nationality.data or None,
            address=form.address.data or None,
            city=form.city.data or None,
            
            phone=form.phone.data or None,
            email=form.email.data or None,
            emergency_contact_name=form.emergency_contact_name.data or None,
            emergency_contact_phone=form.emergency_contact_phone.data or None,
            insurance_provider=form.insurance_provider.data or None,
            insurance_number=form.insurance_number.data or None,
            assigned_dentist_id=form.assigned_dentist_id.data or None,
            photo_path=photo_path,
            anamnesis_pt=form.anamnesis_pt.data or None,
            anamnesis_en=form.anamnesis_en.data or None,
            anamnesis_es=form.anamnesis_es.data or None,
            allergies_pt=form.allergies_pt.data or None,
            allergies_en=form.allergies_en.data or None,
            allergies_es=form.allergies_es.data or None,
            medications_pt=form.medications_pt.data or None,
            medications_en=form.medications_en.data or None,
            medications_es=form.medications_es.data or None,
            chronic_conditions_pt=form.chronic_conditions_pt.data or None,
            chronic_conditions_en=form.chronic_conditions_en.data or None,
            chronic_conditions_es=form.chronic_conditions_es.data or None,
            is_active=True,
        )
        db.session.add(patient)
        try:
            db.session.flush()  # get patient.id before commit
        except IntegrityError:
            db.session.rollback()
            form.id_doc.errors.append(_('Já existe um paciente com este documento de identificação.'))
            return render_template('patients/form.html', form=form, patient=None,
                                   title=_('Novo Paciente'))

        # ── Auto-create patient user account ──
        temp_pw    = _generate_temp_password()
        username   = _generate_patient_username(
            patient.full_name,
            email  = form.email.data or None,
            id_doc = id_doc_val,
        )
        patient_email = form.email.data.strip() if form.email.data else f'{username}@clinica.local'
        user = User(
            username      = username,
            email         = patient_email,
            full_name     = patient.full_name,
            role          = Role.PATIENT,
            password_hash = generate_password_hash(temp_pw, method='pbkdf2:sha256'),
            is_active     = True,
        )
        db.session.add(user)
        try:
            db.session.flush()
            patient.user_id = user.id
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.id_doc.errors.append(_('Já existe um paciente com este documento de identificação.'))
            return render_template('patients/form.html', form=form, patient=None,
                                   title=_('Novo Paciente'))

        log_action('patients', 'CREATE', record_id=patient.id,
                   description=f'Patient created: {patient.full_name}')

        # Store credentials so the detail page can display them once
        session['new_patient_creds'] = {'username': username, 'password': temp_pw}

        flash(_('Paciente criado com sucesso!'), 'success')
        return redirect(url_for('patients.detail', patient_id=patient.id))

    return render_template('patients/form.html', form=form, patient=None, title=_('Novo Paciente'))


@patients_bp.route('/<int:patient_id>')
@login_required
def detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)

    if current_user.role == Role.PATIENT:
        own = Patient.query.filter_by(user_id=current_user.id).first()
        if not own or own.id != patient_id:
            abort(403)
    elif current_user.role == Role.DENTIST:
        if patient.assigned_dentist_id != current_user.id:
            # Check approved care team membership
            ct = PatientCareTeam.query.filter_by(
                patient_id=patient_id, dentist_id=current_user.id, status='approved'
            ).first()
            if not ct:
                abort(403)

    sessions = (ClinicalSession.query
                .filter_by(patient_id=patient_id)
                .order_by(ClinicalSession.session_date.desc())
                .limit(20).all())
    from datetime import date as _date
    new_creds = session.pop('new_patient_creds', None)

    # Care team data
    all_dentists = User.query.filter_by(role=Role.DENTIST, is_active=True).all()
    care_team_entries = PatientCareTeam.query.filter_by(patient_id=patient_id).order_by(PatientCareTeam.created_at.desc()).all()
    # Dentist ids already in care team or the assigned dentist (exclude from request dropdown)
    care_team_dentist_ids = {e.dentist_id for e in care_team_entries if e.status in ('pending', 'approved')}
    if patient.assigned_dentist_id:
        care_team_dentist_ids.add(patient.assigned_dentist_id)
    available_dentists = [d for d in all_dentists if d.id not in care_team_dentist_ids]

    return render_template('patients/detail.html', patient=patient, sessions=sessions,
                           now_date=_date.today(), new_creds=new_creds,
                           care_team_entries=care_team_entries,
                           available_dentists=available_dentists)


@patients_bp.route('/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(patient_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.RECEPTION, Role.DENTIST]:
        abort(403)
    patient = Patient.query.get_or_404(patient_id)

    # Dentists may only edit their own assigned patients
    if current_user.role == Role.DENTIST:
        if patient.assigned_dentist_id != current_user.id:
            abort(403)

    form = PatientForm(obj=patient)
    form.assigned_dentist_id.choices = _dentist_choices()

    if form.validate_on_submit():
        old_name = patient.full_name

        old_snapshot = {
            'full_name':   patient.full_name,
            'id_doc':      patient.id_doc,
            'phone':       patient.phone,
            'email':       patient.email,
            'address':     patient.address,
            'city':        patient.city,
            'nationality': patient.nationality,
            'gender':      patient.gender,
            'date_of_birth': patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            'insurance_provider': patient.insurance_provider,
            'insurance_number':   patient.insurance_number,
            'is_active':   patient.is_active,
        }

        id_doc_val = form.id_doc.data.strip() if form.id_doc.data else None
        if id_doc_val:
            conflict = Patient.query.filter(
                Patient.id_doc == id_doc_val,
                Patient.id != patient.id
            ).first()
            if conflict:
                form.id_doc.errors.append(
                    _('Já existe um paciente com este documento de identificação (%(name)s).',
                      name=conflict.full_name)
                )
                return render_template('patients/form.html', form=form, patient=patient,
                                       title=_('Editar Paciente'))

        if form.photo.data and form.photo.data.filename:
            photo_path = _save_photo(form.photo.data)
            if photo_path:
                patient.photo_path = photo_path

        patient.full_name = form.full_name.data
        patient.date_of_birth = form.date_of_birth.data
        patient.gender = form.gender.data or None
        patient.id_doc = id_doc_val
        patient.nationality = form.nationality.data or None
        patient.address = form.address.data or None
        patient.city = form.city.data or None
        
        patient.phone = form.phone.data or None
        patient.email = form.email.data or None
        patient.emergency_contact_name = form.emergency_contact_name.data or None
        patient.emergency_contact_phone = form.emergency_contact_phone.data or None
        patient.insurance_provider = form.insurance_provider.data or None
        patient.insurance_number = form.insurance_number.data or None
        # Dentists cannot unassign themselves; preserve their assignment
        if current_user.role == Role.DENTIST:
            if not form.assigned_dentist_id.data or form.assigned_dentist_id.data == 0:
                patient.assigned_dentist_id = current_user.id
            else:
                patient.assigned_dentist_id = form.assigned_dentist_id.data
        else:
            patient.assigned_dentist_id = form.assigned_dentist_id.data or None
        patient.anamnesis_pt = form.anamnesis_pt.data or None
        patient.anamnesis_en = form.anamnesis_en.data or None
        patient.anamnesis_es = form.anamnesis_es.data or None
        patient.allergies_pt = form.allergies_pt.data or None
        patient.allergies_en = form.allergies_en.data or None
        patient.allergies_es = form.allergies_es.data or None
        patient.medications_pt = form.medications_pt.data or None
        patient.medications_en = form.medications_en.data or None
        patient.medications_es = form.medications_es.data or None
        patient.chronic_conditions_pt = form.chronic_conditions_pt.data or None
        patient.chronic_conditions_en = form.chronic_conditions_en.data or None
        patient.chronic_conditions_es = form.chronic_conditions_es.data or None
        patient.is_active = form.is_active.data
        patient.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.id_doc.errors.append(_('Já existe um paciente com este documento de identificação.'))
            return render_template('patients/form.html', form=form, patient=patient,
                                   title=_('Editar Paciente'))
        log_action('patients', 'UPDATE', record_id=patient.id,
                   old_value=old_snapshot,
                   description=f'Patient updated: {old_name}')
        flash(_('Paciente atualizado com sucesso!'), 'success')
        return redirect(url_for('patients.detail', patient_id=patient.id))

    if request.method == 'GET':
        form.assigned_dentist_id.data = patient.assigned_dentist_id or 0

    return render_template('patients/form.html', form=form, patient=patient,
                           title=_('Editar Paciente'))


@patients_bp.route('/<int:patient_id>/delete', methods=['POST'])
@login_required
def delete(patient_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    patient = Patient.query.get_or_404(patient_id)
    name = patient.full_name
    from ..models import SessionTreatment, Prescription, XRay, SessionAddendum, EvolutionPhoto, Appointment
    for sess in patient.sessions.all():
        SessionTreatment.query.filter_by(session_id=sess.id).delete()
        Prescription.query.filter_by(session_id=sess.id).delete()
        XRay.query.filter_by(session_id=sess.id).delete()
        SessionAddendum.query.filter_by(session_id=sess.id).delete()
        db.session.delete(sess)
    EvolutionPhoto.query.filter_by(patient_id=patient_id).delete()
    Appointment.query.filter_by(patient_id=patient_id).delete()
    db.session.delete(patient)
    db.session.commit()
    log_action('patients', 'DELETE', record_id=patient_id,
               description=f'Patient permanently deleted: {name}')
    flash(_('Paciente eliminado permanentemente.'), 'danger')
    return redirect(url_for('patients.index'))


@patients_bp.route('/<int:patient_id>/deactivate', methods=['POST'])
@login_required
def deactivate(patient_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    patient = Patient.query.get_or_404(patient_id)
    patient.is_active = False
    db.session.commit()
    log_action('patients', 'DELETE', record_id=patient_id,
               description=f'Patient soft-deleted: {patient.full_name}')
    flash(_('Paciente desativado.'), 'warning')
    return redirect(url_for('patients.index'))


# ── Care Team ─────────────────────────────────────────────────────────────────

@patients_bp.route('/<int:patient_id>/care-team/request', methods=['POST'])
@login_required
def care_team_request(patient_id):
    """Dentist (or superadmin/director) proposes another dentist to share access."""
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]:
        abort(403)
    patient = Patient.query.get_or_404(patient_id)
    dentist_id = request.form.get('dentist_id', type=int)
    notes = request.form.get('notes', '').strip()
    if not dentist_id:
        flash(_('Selecione um dentista.'), 'warning')
        return redirect(url_for('patients.detail', patient_id=patient_id))
    dentist = User.query.get(dentist_id)
    if not dentist or dentist.role != Role.DENTIST:
        flash(_('Dentista inválido.'), 'danger')
        return redirect(url_for('patients.detail', patient_id=patient_id))
    # Avoid duplicates
    existing = PatientCareTeam.query.filter_by(
        patient_id=patient_id, dentist_id=dentist_id
    ).filter(PatientCareTeam.status.in_(['pending', 'approved'])).first()
    if existing:
        flash(_('Este dentista já tem acesso ou pedido pendente.'), 'warning')
        return redirect(url_for('patients.detail', patient_id=patient_id))
    entry = PatientCareTeam(
        patient_id=patient_id,
        dentist_id=dentist_id,
        requested_by_id=current_user.id,
        status='pending',
        notes=notes,
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(entry)
    db.session.commit()
    log_action('patients', 'UPDATE', record_id=patient_id,
               description=f'Care team request: dentist {dentist.full_name} added to patient {patient.full_name} by {current_user.full_name}')
    flash(_('Pedido de acesso enviado. Aguarda aprovação do Diretor/Superadmin.'), 'success')
    return redirect(url_for('patients.detail', patient_id=patient_id))


@patients_bp.route('/<int:patient_id>/care-team/<int:entry_id>/approve', methods=['POST'])
@login_required
def care_team_approve(patient_id, entry_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    entry = PatientCareTeam.query.get_or_404(entry_id)
    if entry.patient_id != patient_id:
        abort(404)
    entry.status = 'approved'
    entry.approved_by_id = current_user.id
    entry.resolved_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action('patients', 'UPDATE', record_id=patient_id,
               description=f'Care team approved: dentist {entry.dentist.full_name} for patient id={patient_id}')
    flash(_('Acesso aprovado.'), 'success')
    return redirect(url_for('patients.detail', patient_id=patient_id))


@patients_bp.route('/<int:patient_id>/care-team/<int:entry_id>/reject', methods=['POST'])
@login_required
def care_team_reject(patient_id, entry_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    entry = PatientCareTeam.query.get_or_404(entry_id)
    if entry.patient_id != patient_id:
        abort(404)
    entry.status = 'rejected'
    entry.approved_by_id = current_user.id
    entry.resolved_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action('patients', 'UPDATE', record_id=patient_id,
               description=f'Care team rejected: dentist {entry.dentist.full_name} for patient id={patient_id}')
    flash(_('Pedido recusado.'), 'warning')
    return redirect(url_for('patients.detail', patient_id=patient_id))


@patients_bp.route('/<int:patient_id>/care-team/<int:entry_id>/remove', methods=['POST'])
@login_required
def care_team_remove(patient_id, entry_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    entry = PatientCareTeam.query.get_or_404(entry_id)
    if entry.patient_id != patient_id:
        abort(404)
    dentist_name = entry.dentist.full_name
    db.session.delete(entry)
    db.session.commit()
    log_action('patients', 'UPDATE', record_id=patient_id,
               description=f'Care team removed: dentist {dentist_name} from patient id={patient_id}')
    flash(_('Dentista removido da equipa clínica.'), 'info')
    return redirect(url_for('patients.detail', patient_id=patient_id))


@patients_bp.route('/care-team-pending')
@login_required
def care_team_pending():
    """Page listing all pending care team requests — for superadmin/director."""
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    pending = (PatientCareTeam.query
               .filter_by(status='pending')
               .order_by(PatientCareTeam.created_at.asc())
               .all())
    return render_template('patients/care_team_pending.html', pending=pending)
