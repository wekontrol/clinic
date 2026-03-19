from flask import render_template, redirect, url_for, flash, request, abort, Response, current_app
from flask_login import login_required, current_user
from flask_babel import gettext as _

from . import admin_bp
from .forms import TreatmentForm, MedicineForm, UserForm
from ..models import Treatment, Medicine, User, AppSetting, Patient, PatientCareTeam, Appointment, ClinicalSession
from ..extensions import db
from ..decorators import role_required, director_or_superadmin_required
from ..audit import log_action
from ..models import Role


def _clinical_staff_check():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]:
        abort(403)


# ─── TREATMENTS ──────────────────────────────────────────────────────────────

@admin_bp.route('/treatments')
@login_required
def treatments():
    _clinical_staff_check()
    page = request.args.get('page', 1, type=int)
    query = Treatment.query.order_by(Treatment.name_pt)
    if request.args.get('inactive') != '1':
        query = query.filter_by(is_active=True)
    treatments = query.paginate(page=page, per_page=20)
    return render_template('admin/treatments/index.html', treatments=treatments)


@admin_bp.route('/treatments/new', methods=['GET', 'POST'])
@login_required
def new_treatment():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    form = TreatmentForm()
    if form.validate_on_submit():
        treatment = Treatment(
            name_pt=form.name_pt.data,
            name_en=form.name_en.data,
            name_es=form.name_es.data,
            description_pt=form.description_pt.data,
            description_en=form.description_en.data,
            description_es=form.description_es.data,
            category=form.category.data,
            price=form.price.data,
            duration_minutes=form.duration_minutes.data,
            is_active=form.is_active.data,
            created_by_id=current_user.id
        )
        db.session.add(treatment)
        db.session.commit()
        log_action('treatments', 'CREATE', record_id=treatment.id,
                   new_value={'name_pt': treatment.name_pt}, description='Treatment created')
        flash(_('Tratamento criado com sucesso!'), 'success')
        return redirect(url_for('admin.treatments'))
    return render_template('admin/treatments/form.html', form=form, title=_('Novo Tratamento'))


@admin_bp.route('/treatments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_treatment(id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    treatment = Treatment.query.get_or_404(id)
    form = TreatmentForm(obj=treatment)
    if form.validate_on_submit():
        old = {'name_pt': treatment.name_pt}
        form.populate_obj(treatment)
        db.session.commit()
        log_action('treatments', 'UPDATE', record_id=treatment.id,
                   old_value=old, new_value={'name_pt': treatment.name_pt},
                   description='Treatment updated')
        flash(_('Tratamento atualizado com sucesso!'), 'success')
        return redirect(url_for('admin.treatments'))
    return render_template('admin/treatments/form.html', form=form,
                           title=_('Editar Tratamento'), treatment=treatment)


@admin_bp.route('/treatments/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_treatment(id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    treatment = Treatment.query.get_or_404(id)
    treatment.is_active = not treatment.is_active
    db.session.commit()
    log_action('treatments', 'UPDATE', record_id=treatment.id,
               description=f'Treatment {"activated" if treatment.is_active else "deactivated"}')
    flash(_('Estado do tratamento alterado.'), 'info')
    return redirect(url_for('admin.treatments'))


# ─── MEDICINES ───────────────────────────────────────────────────────────────

@admin_bp.route('/medicines')
@login_required
def medicines():
    _clinical_staff_check()
    page = request.args.get('page', 1, type=int)
    query = Medicine.query.order_by(Medicine.name_pt)
    if request.args.get('inactive') != '1':
        query = query.filter_by(is_active=True)
    medicines = query.paginate(page=page, per_page=20)
    return render_template('admin/medicines/index.html', medicines=medicines)


@admin_bp.route('/medicines/new', methods=['GET', 'POST'])
@login_required
def new_medicine():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    form = MedicineForm()
    if form.validate_on_submit():
        medicine = Medicine(
            name_pt=form.name_pt.data,
            name_en=form.name_en.data,
            name_es=form.name_es.data,
            active_ingredient=form.active_ingredient.data,
            dosage_form=form.dosage_form.data,
            strength=form.strength.data,
            instructions_pt=form.instructions_pt.data,
            instructions_en=form.instructions_en.data,
            instructions_es=form.instructions_es.data,
            contraindications_pt=form.contraindications_pt.data,
            contraindications_en=form.contraindications_en.data,
            contraindications_es=form.contraindications_es.data,
            is_active=form.is_active.data,
            created_by_id=current_user.id
        )
        db.session.add(medicine)
        db.session.commit()
        log_action('medicines', 'CREATE', record_id=medicine.id,
                   new_value={'name_pt': medicine.name_pt}, description='Medicine created')
        flash(_('Medicamento criado com sucesso!'), 'success')
        return redirect(url_for('admin.medicines'))
    return render_template('admin/medicines/form.html', form=form, title=_('Novo Medicamento'))


@admin_bp.route('/medicines/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_medicine(id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    medicine = Medicine.query.get_or_404(id)
    form = MedicineForm(obj=medicine)
    if form.validate_on_submit():
        old = {'name_pt': medicine.name_pt}
        form.populate_obj(medicine)
        db.session.commit()
        log_action('medicines', 'UPDATE', record_id=medicine.id,
                   old_value=old, new_value={'name_pt': medicine.name_pt},
                   description='Medicine updated')
        flash(_('Medicamento atualizado com sucesso!'), 'success')
        return redirect(url_for('admin.medicines'))
    return render_template('admin/medicines/form.html', form=form,
                           title=_('Editar Medicamento'), medicine=medicine)


@admin_bp.route('/medicines/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_medicine(id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    medicine = Medicine.query.get_or_404(id)
    medicine.is_active = not medicine.is_active
    db.session.commit()
    log_action('medicines', 'UPDATE', record_id=medicine.id,
               description=f'Medicine {"activated" if medicine.is_active else "deactivated"}')
    flash(_('Estado do medicamento alterado.'), 'info')
    return redirect(url_for('admin.medicines'))


# ─── USERS ────────────────────────────────────────────────────────────────────
#
# Matriz de permissões RBAC para gestão de utilizadores:
#   _ROLE_CAN_ASSIGN  – que roles cada utilizador pode atribuir a outros
#   _ROLE_CAN_VIEW    – que roles cada utilizador pode ver na lista (None = todos)
#
_ROLE_CAN_ASSIGN = {
    Role.SUPERADMIN:        {'superadmin', 'clinical_director', 'dentist', 'patient', 'reception'},
    Role.CLINICAL_DIRECTOR: {'dentist', 'patient', 'reception'},
    Role.DENTIST:           {'patient'},
    Role.RECEPTION:         {'patient'},
}

_ROLE_CAN_VIEW = {
    Role.SUPERADMIN:        None,
    Role.CLINICAL_DIRECTOR: None,
    Role.DENTIST:           {'patient'},
    Role.RECEPTION:         {'patient'},
}

_USERS_ALLOWED = {Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST, Role.RECEPTION}

_ALL_ROLE_CHOICES = [
    ('superadmin',        'Superadmin'),
    ('clinical_director', 'Diretor Clínico'),
    ('dentist',           'Dentista'),
    ('patient',           'Paciente'),
    ('reception',         'Recepção'),
]


def _allowed_roles_for_current_user():
    return _ROLE_CAN_ASSIGN.get(current_user.role, set())


def _apply_role_choices(form):
    allowed = _allowed_roles_for_current_user()
    form.role.choices = [(v, l) for v, l in _ALL_ROLE_CHOICES if v in allowed]


def _user_list_query():
    view_filter = _ROLE_CAN_VIEW.get(current_user.role)
    q = User.query
    if view_filter is not None:
        q = q.filter(User.role.in_(view_filter))
    return q


@admin_bp.route('/users')
@login_required
def users():
    if current_user.role not in _USERS_ALLOWED:
        abort(403)
    page        = request.args.get('page', 1, type=int)
    search      = request.args.get('q', '').strip()
    role_f      = request.args.get('role', '').strip()
    since_f     = request.args.get('since', '').strip()
    status_f    = request.args.get('status', '').strip()

    query = _user_list_query().order_by(User.full_name)

    if search:
        query = query.filter(User.full_name.ilike(f'%{search}%'))
    if role_f:
        query = query.filter(User.role == role_f)
    if status_f == 'active':
        query = query.filter(User.is_active == True)
    elif status_f == 'inactive':
        query = query.filter(User.is_active == False)
    if since_f:
        try:
            from datetime import datetime as _dt
            since_date = _dt.strptime(since_f, '%Y-%m-%d')
            query = query.filter(User.created_at >= since_date)
        except Exception:
            pass

    users_page = query.paginate(page=page, per_page=20)
    return render_template('admin/users/index.html', users=users_page,
                           filter_role=role_f, filter_since=since_f, filter_status=status_f)


@admin_bp.route('/users/<int:uid>/reset-password', methods=['POST'])
@login_required
def reset_user_password(uid):
    if current_user.role not in {Role.SUPERADMIN, Role.CLINICAL_DIRECTOR}:
        abort(403)
    user = User.query.get_or_404(uid)
    if current_user.role == Role.CLINICAL_DIRECTOR and user.role == Role.SUPERADMIN:
        abort(403)
    if user.id == current_user.id:
        flash(_('Use o formulário de perfil para alterar a sua própria senha.'), 'warning')
        return redirect(url_for('admin.users'))
    from werkzeug.security import generate_password_hash
    new_pw = 'changeme123'
    user.password_hash = generate_password_hash(new_pw, method='pbkdf2:sha256')
    db.session.commit()
    log_action('users', 'UPDATE', record_id=user.id,
               description=f'Password reset by {current_user.username}')
    flash(_('Senha de %(u)s redefinida para: changeme123', u=user.username), 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
def new_user():
    if current_user.role not in _USERS_ALLOWED:
        abort(403)
    form = UserForm()
    _apply_role_choices(form)
    if form.validate_on_submit():
        from werkzeug.security import generate_password_hash
        if form.role.data not in _allowed_roles_for_current_user():
            flash(_('Não tem permissão para atribuir este perfil.'), 'danger')
            return render_template('admin/users/form.html', form=form, title=_('Novo Utilizador'))
        existing = User.query.filter_by(username=form.username.data).first()
        if existing:
            flash(_('Nome de utilizador já existe.'), 'danger')
            return render_template('admin/users/form.html', form=form, title=_('Novo Utilizador'))
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data,
            role=form.role.data,
            phone=form.phone.data,
            specialty=form.specialty.data,
            is_active=form.is_active.data,
            password_hash=generate_password_hash('changeme123', method='pbkdf2:sha256')
        )
        db.session.add(user)
        db.session.commit()
        log_action('users', 'CREATE', record_id=user.id,
                   new_value={'username': user.username, 'role': user.role},
                   description='User created')
        flash(_('Utilizador criado! Senha inicial: changeme123'), 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/users/form.html', form=form, title=_('Novo Utilizador'))


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    if current_user.role not in _USERS_ALLOWED:
        abort(403)
    user = User.query.get_or_404(id)
    view_filter = _ROLE_CAN_VIEW.get(current_user.role)
    if view_filter is not None and user.role not in view_filter:
        abort(403)
    form = UserForm(obj=user)
    _apply_role_choices(form)
    if form.validate_on_submit():
        if form.role.data not in _allowed_roles_for_current_user():
            flash(_('Não tem permissão para atribuir este perfil.'), 'danger')
            return render_template('admin/users/form.html', form=form,
                                   title=_('Editar Utilizador'), user=user)
        old = {'username': user.username, 'role': user.role}
        user.username = form.username.data
        user.email = form.email.data
        user.full_name = form.full_name.data
        user.role = form.role.data
        user.phone = form.phone.data
        user.specialty = form.specialty.data
        user.is_active = form.is_active.data
        db.session.commit()
        log_action('users', 'UPDATE', record_id=user.id,
                   old_value=old, new_value={'username': user.username, 'role': user.role},
                   description='User updated')
        flash(_('Utilizador atualizado com sucesso!'), 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/users/form.html', form=form,
                           title=_('Editar Utilizador'), user=user)


@admin_bp.route('/users/<int:uid>/delete', methods=['POST'])
@login_required
def delete_user(uid):
    if current_user.role != Role.SUPERADMIN:
        abort(403)
    user = User.query.get_or_404(uid)
    if user.id == current_user.id:
        flash(_('Não pode eliminar a sua própria conta.'), 'danger')
        return redirect(url_for('admin.users'))
    if user.role == Role.SUPERADMIN:
        flash(_('Não é possível eliminar um Superadministrador.'), 'danger')
        return redirect(url_for('admin.users'))

    # ── Transfer patients/sessions when deleting a dentist / clinical director ─
    if user.role in (Role.DENTIST, Role.CLINICAL_DIRECTOR):
        director = (
            User.query.filter(
                User.role == Role.CLINICAL_DIRECTOR,
                User.is_active == True,
                User.id != uid,
            ).first()
            or User.query.filter(
                User.role == Role.SUPERADMIN,
                User.id != uid,
            ).first()
        )
        new_dentist_id = director.id if director else current_user.id

        # Transfer assigned patients
        Patient.query.filter_by(assigned_dentist_id=uid).update(
            {'assigned_dentist_id': new_dentist_id}, synchronize_session=False)

        # Transfer ALL appointments (ClinicalSession.dentist_id is NOT NULL)
        Appointment.query.filter_by(dentist_id=uid).update(
            {'dentist_id': new_dentist_id}, synchronize_session=False)

        # Transfer clinical sessions so NOT NULL FK constraint is satisfied
        ClinicalSession.query.filter_by(dentist_id=uid).update(
            {'dentist_id': new_dentist_id}, synchronize_session=False)

        # Remove care-team entries for this dentist
        PatientCareTeam.query.filter_by(dentist_id=uid).delete()

        if director:
            flash(_(
                'Os pacientes e sessões de %(u)s foram transferidos para %(d)s.',
                u=user.full_name, d=director.full_name,
            ), 'info')

    log_action('users', 'DELETE', record_id=user.id,
               description=f'User {user.username} ({user.role}) deleted by {current_user.username}')
    db.session.delete(user)
    db.session.commit()
    flash(_('Utilizador %(u)s eliminado com sucesso.', u=user.full_name), 'success')
    return redirect(url_for('admin.users'))


# ─── AUDIT LOG ────────────────────────────────────────────────────────────────

@admin_bp.route('/audit')
@login_required
@director_or_superadmin_required
def audit_log():
    from ..models import AuditLog
    page = request.args.get('page', 1, type=int)
    query = AuditLog.query.order_by(AuditLog.timestamp.desc())

    if request.args.get('user_id'):
        query = query.filter_by(user_id=request.args.get('user_id', type=int))
    if request.args.get('action'):
        query = query.filter_by(action=request.args.get('action'))
    if request.args.get('table'):
        query = query.filter_by(table_name=request.args.get('table'))

    logs = query.paginate(page=page, per_page=30)
    users = User.query.order_by(User.full_name).all()
    return render_template('admin/audit_log.html', logs=logs, users=users)


@admin_bp.route('/audit/<int:log_id>/rollback', methods=['POST'])
@login_required
@director_or_superadmin_required
def audit_rollback(log_id):
    from ..models import AuditLog, Patient, ClinicalSession
    from ..extensions import db
    from ..audit import log_action
    from datetime import date as _date

    entry = AuditLog.query.get_or_404(log_id)

    if entry.action != 'UPDATE' or not entry.old_value or not entry.record_id:
        flash(_('Este registo não suporta reversão automática.'), 'warning')
        return redirect(url_for('admin.audit_log'))

    table = entry.table_name
    rid   = entry.record_id
    ov    = entry.old_value

    try:
        if table == 'patients':
            patient = Patient.query.get(rid)
            if not patient:
                flash(_('Paciente não encontrado (ID %(id)d).', id=rid), 'danger')
                return redirect(url_for('admin.audit_log'))
            if 'full_name'    in ov: patient.full_name    = ov['full_name']
            if 'id_doc'       in ov: patient.id_doc       = ov['id_doc']
            if 'phone'        in ov: patient.phone        = ov['phone']
            if 'email'        in ov: patient.email        = ov['email']
            if 'address'      in ov: patient.address      = ov['address']
            if 'city'         in ov: patient.city         = ov['city']
            if 'nationality'  in ov: patient.nationality  = ov['nationality']
            if 'gender'       in ov: patient.gender       = ov['gender']
            if 'insurance_provider' in ov: patient.insurance_provider = ov['insurance_provider']
            if 'insurance_number'   in ov: patient.insurance_number   = ov['insurance_number']
            if 'is_active'    in ov: patient.is_active    = ov['is_active']
            if 'date_of_birth' in ov and ov['date_of_birth']:
                try:
                    patient.date_of_birth = _date.fromisoformat(ov['date_of_birth'])
                except ValueError:
                    pass
            db.session.commit()
            log_action('patients', 'ROLLBACK', record_id=rid,
                       description=f'Rollback from audit #{log_id}')
            flash(_('Dados do paciente revertidos com sucesso (auditoria #%(id)d).', id=log_id), 'success')

        elif table == 'clinical_sessions':
            sess = ClinicalSession.query.get(rid)
            if not sess:
                flash(_('Sessão não encontrada (ID %(id)d).', id=rid), 'danger')
                return redirect(url_for('admin.audit_log'))
            if 'status'          in ov: sess.status          = ov['status']
            if 'chief_complaint' in ov: sess.chief_complaint = ov['chief_complaint']
            if 'clinical_notes'  in ov: sess.clinical_notes  = ov['clinical_notes']
            if 'diagnosis'       in ov: sess.diagnosis       = ov['diagnosis']
            if 'treatment_plan'  in ov: sess.treatment_plan  = ov['treatment_plan']
            if 'bp_systolic'     in ov: sess.bp_systolic     = ov['bp_systolic']
            if 'bp_diastolic'    in ov: sess.bp_diastolic    = ov['bp_diastolic']
            if 'heart_rate'      in ov: sess.heart_rate      = ov['heart_rate']
            db.session.commit()
            log_action('clinical_sessions', 'ROLLBACK', record_id=rid,
                       description=f'Rollback from audit #{log_id}')
            flash(_('Sessão revertida com sucesso (auditoria #%(id)d).', id=log_id), 'success')

        else:
            flash(_('Reversão automática não suportada para a tabela "%(t)s".', t=table), 'warning')

    except Exception as exc:
        db.session.rollback()
        flash(_('Erro ao reverter: %(e)s', e=str(exc)), 'danger')

    return redirect(url_for('admin.audit_log'))


# ─── PDF TEMPLATE EDITOR ──────────────────────────────────────────────────────

_PDF_TYPES = {
    'treatment_plan': {
        'prefix':   'tp',
        'label':    'Plano de Tratamento',
        'icon':     'bi-file-medical-fill',
        'color':    '#14b8a6',
        'desc':     'Documento clínico com diagnóstico, plano de tratamento e procedimentos realizados.',
    },
    'consent_form': {
        'prefix':   'cf',
        'label':    'Consentimento Informado',
        'icon':     'bi-pen-fill',
        'color':    '#00d97e',
        'desc':     'Termo de consentimento informado a assinar pelo paciente antes do tratamento.',
    },
    'prescription': {
        'prefix':   'rx',
        'label':    'Receita Médica',
        'icon':     'bi-prescription2',
        'color':    '#e5a430',
        'desc':     'Receita médica com lista de medicamentos, dosagens e instruções de toma.',
    },
}


@admin_bp.route('/pdf-templates')
@login_required
@director_or_superadmin_required
def pdf_templates():
    return render_template('admin/pdf_templates/index.html', pdf_types=_PDF_TYPES)


@admin_bp.route('/pdf-templates/<ptype>/edit', methods=['GET', 'POST'])
@login_required
@director_or_superadmin_required
def pdf_template_edit(ptype):
    if ptype not in _PDF_TYPES:
        abort(404)
    meta   = _PDF_TYPES[ptype]
    prefix = meta['prefix']

    if request.method == 'POST':
        # Save all per-type fields using the full type name as key prefix
        # Key format: pdf_{ptype}_{field}[_{locale}]  e.g. pdf_treatment_plan_title_pt
        for key, val in request.form.items():
            if (key.startswith(f'pdf_{ptype}_')
                    and not key.endswith('_show_logo')
                    and not key.endswith('_show_pagenum')):
                AppSetting.set(key, val.strip())

        for cb in (f'pdf_{ptype}_show_logo', f'pdf_{ptype}_show_pagenum'):
            AppSetting.set(cb, '1' if request.form.get(cb) else '0')

        flash(_('Configurações do PDF guardadas com sucesso.'), 'success')
        return redirect(url_for('admin.pdf_template_edit', ptype=ptype))

    settings = AppSetting.all_as_dict()
    return render_template('admin/pdf_templates/form.html',
                           ptype=ptype, meta=meta, prefix=prefix, settings=settings)


@admin_bp.route('/pdf-templates/<ptype>/preview')
@login_required
@director_or_superadmin_required
def pdf_template_preview(ptype):
    """Generate a mock PDF with sample data and serve inline for preview."""
    if ptype not in _PDF_TYPES:
        abort(404)
    from types import SimpleNamespace
    from datetime import date as _date

    mock_patient = SimpleNamespace(full_name='Ana Beatriz Ferreira', id=0)
    mock_dentist = SimpleNamespace(
        full_name='Dr. João Manuel Costa', id=0, signature_path=None)
    mock_session = SimpleNamespace(
        id=0,
        session_code='SES-DEMO-001',
        session_date=_date.today(),
        patient=mock_patient,
        dentist=mock_dentist,
        diagnosis='Cárie profunda no dente 36 com envolvimento pulpar. Periodontite leve generalizada.',
        clinical_notes='Paciente refere dor ao mastigar há 3 semanas. Sensibilidade ao frio no quadrante inferior esquerdo.',
        treatment_plan='Endodontia no dente 36 seguida de coroa metalo-cerâmica. Raspagem e alisamento radicular.',
        chief_complaint='Dor ao mastigar',
    )

    upload_folder = current_app.config.get('UPLOAD_FOLDER', '')

    from ..pdfs import (generate_treatment_plan_pdf,
                        generate_consent_form_pdf,
                        generate_prescription_pdf)

    if ptype == 'treatment_plan':
        mock_tmt = SimpleNamespace(
            treatment=SimpleNamespace(
                name_for_locale=lambda l: 'Endodontia (Tratamento de Canal)',
                price=45000,
            ),
            price_at_time=45000,
            quantity=1,
        )
        mock_tmt2 = SimpleNamespace(
            treatment=SimpleNamespace(
                name_for_locale=lambda l: 'Destartarização Completa',
                price=12000,
            ),
            price_at_time=12000,
            quantity=1,
        )
        pdf_bytes = generate_treatment_plan_pdf(
            mock_session, locale='pt', upload_folder=upload_folder,
            _treatments=[mock_tmt, mock_tmt2])

    elif ptype == 'consent_form':
        pdf_bytes = generate_consent_form_pdf(
            mock_session, locale='pt', upload_folder=upload_folder)

    else:
        mock_rx = SimpleNamespace(
            medicine=SimpleNamespace(name_for_locale=lambda l: 'Amoxicilina'),
            dosage='500 mg', frequency='8/8h', duration='7 dias',
            instructions='Tomar com alimentos. Completar o ciclo antibiótico.',
        )
        mock_rx2 = SimpleNamespace(
            medicine=SimpleNamespace(name_for_locale=lambda l: 'Ibuprofeno'),
            dosage='400 mg', frequency='12/12h', duration='5 dias',
            instructions='Tomar após as refeições.',
        )
        pdf_bytes = generate_prescription_pdf(
            mock_session, locale='pt', upload_folder=upload_folder,
            _prescriptions=[mock_rx, mock_rx2])

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': 'inline; filename="preview.pdf"'},
    )
