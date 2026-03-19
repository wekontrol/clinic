import os
import uuid
import json
from datetime import datetime, timezone, date as _date
from flask import (render_template, redirect, url_for, flash, request,
                   abort, current_app, jsonify, send_from_directory)
from flask_login import login_required, current_user
from flask_babel import gettext as _

from . import sessions_bp
from .forms import SessionForm, PrescriptionForm, XRayUploadForm, EvolutionPhotoForm, AddendumForm
from ..models import (ClinicalSession, SessionAddendum, SessionStatus, Appointment, Patient, Treatment,
                      SessionTreatment, Prescription, Medicine, XRay, EvolutionPhoto,
                      AuditLog, User, Role, ImmutableSessionError, AppSetting,
                      StockProduct, StockMovement, SessionConsumable)
from ..extensions import db
from ..audit import log_action


ALLOWED_XRAY = {'jpg', 'jpeg', 'png', 'pdf'}
ALLOWED_PHOTO = {'jpg', 'jpeg', 'png'}


def _allowed(filename, allowed):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def _urgency_price(base_price, surcharge_pct):
    """Return (final_price, applied_pct) after applying urgency surcharge."""
    if base_price is None:
        return None, None
    if surcharge_pct and float(surcharge_pct) > 0:
        factor = 1 + float(surcharge_pct) / 100
        return round(float(base_price) * factor, 2), float(surcharge_pct)
    return float(base_price), None


def _get_surcharge_pct(sess):
    """Return urgency surcharge % if session is an emergency, else None."""
    if not sess.appointment_id:
        return None
    apt = Appointment.query.get(sess.appointment_id)
    if apt and apt.is_emergency:
        return AppSetting.get('urgency_surcharge', '30')
    return None


def _save_file(file, subfolder, allowed):
    """Save an uploaded file; return relative path or None on error."""
    if not file or not file.filename:
        return None
    if not _allowed(file.filename, allowed):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    file.save(os.path.join(dest_dir, fname))
    return os.path.join(subfolder, fname)


def _can_edit_session(session):
    """Return True if current user may still edit the session."""
    if session.status == SessionStatus.CLOSED:
        return False
    if current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        return True
    if current_user.role == Role.DENTIST and session.dentist_id == current_user.id:
        return True
    return False


def _generate_session_code():
    today = _date.today().strftime('%Y%m%d')
    prefix = f'SES-{today}-'
    last = (ClinicalSession.query
            .filter(ClinicalSession.session_code.like(f'{prefix}%'))
            .order_by(ClinicalSession.session_code.desc())
            .first())
    if last:
        try:
            seq = int(last.session_code.split('-')[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f'{prefix}{seq:04d}'


# ─── SESSION LIST ─────────────────────────────────────────────────────────────

@sessions_bp.route('/')
@login_required
def index():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]:
        abort(403)

    page       = request.args.get('page', 1, type=int)
    f_status   = request.args.get('status', '')
    f_dentist  = request.args.get('dentist_id', '', type=str)
    f_patient  = request.args.get('patient_q', '').strip()
    f_date_from = request.args.get('date_from', '')
    f_date_to   = request.args.get('date_to', '')

    q = ClinicalSession.query.order_by(ClinicalSession.session_date.desc())

    if current_user.role == Role.DENTIST:
        q = q.filter_by(dentist_id=current_user.id)
    elif f_dentist:
        q = q.filter_by(dentist_id=int(f_dentist))

    if f_status:
        q = q.filter_by(status=f_status)

    if f_patient:
        q = q.join(Patient, ClinicalSession.patient_id == Patient.id)\
              .filter(Patient.full_name.ilike(f'%{f_patient}%'))

    if f_date_from:
        try:
            q = q.filter(ClinicalSession.session_date >= datetime.fromisoformat(f_date_from))
        except ValueError:
            pass
    if f_date_to:
        try:
            q = q.filter(ClinicalSession.session_date <= datetime.fromisoformat(f_date_to + 'T23:59:59'))
        except ValueError:
            pass

    sessions = q.paginate(page=page, per_page=20)

    dentists = User.query.filter(User.role.in_(['superadmin', 'clinical_director', 'dentist'])).order_by(User.full_name).all()
    return render_template('sessions/index.html', sessions=sessions, dentists=dentists,
                           f_status=f_status, f_dentist=f_dentist, f_patient=f_patient,
                           f_date_from=f_date_from, f_date_to=f_date_to)


# ─── BULK ACTIONS ─────────────────────────────────────────────────────────────

@sessions_bp.route('/bulk-action', methods=['POST'])
@login_required
def bulk_action():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]:
        abort(403)

    action     = request.form.get('action', '')
    new_status = request.form.get('new_status', '')
    ids        = request.form.getlist('session_ids')

    if not ids:
        flash(_('Nenhuma sessão seleccionada.'), 'warning')
        return redirect(url_for('sessions.index'))

    ids = [int(i) for i in ids]

    if action == 'delete':
        if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
            abort(403)
        count = 0
        for sid in ids:
            sess = ClinicalSession.query.get(sid)
            if sess is None:
                continue
            SessionTreatment.query.filter_by(session_id=sid).delete()
            Prescription.query.filter_by(session_id=sid).delete()
            XRay.query.filter_by(session_id=sid).delete()
            SessionAddendum.query.filter_by(session_id=sid).delete()
            db.session.delete(sess)
            count += 1
        db.session.commit()
        log_action('clinical_sessions', 'DELETE', description=f'Bulk delete {count} sessions')
        flash(_('%(n)d sessão(ões) eliminada(s) permanentemente.', n=count), 'danger')

    elif action == 'set_status' and new_status:
        allowed_statuses = {'in_progress', 'closed', 'scheduled', 'cancelled'}
        if new_status not in allowed_statuses:
            abort(400)
        count = 0
        for sid in ids:
            sess = ClinicalSession.query.get(sid)
            if sess is None:
                continue
            if current_user.role == Role.DENTIST and sess.dentist_id != current_user.id:
                continue
            sess.status = new_status
            count += 1
        db.session.commit()
        log_action('clinical_sessions', 'UPDATE', description=f'Bulk status → {new_status} on {count} sessions')
        flash(_('%(n)d sessão(ões) actualizadas para "%(s)s".', n=count, s=new_status), 'success')
    else:
        flash(_('Acção inválida.'), 'warning')

    return redirect(url_for('sessions.index', **{k: v for k, v in request.args.items()}))


# ─── START / CREATE SESSION FROM APPOINTMENT ──────────────────────────────────

@sessions_bp.route('/start/<int:appointment_id>', methods=['POST'])
@login_required
def start_from_appointment(appointment_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST, Role.RECEPTION]:
        abort(403)
    apt = Appointment.query.get_or_404(appointment_id)
    # Check dentist ownership
    if current_user.role == Role.DENTIST and apt.dentist_id != current_user.id:
        abort(403)

    existing = ClinicalSession.query.filter_by(appointment_id=appointment_id).first()
    if existing:
        return redirect(url_for('sessions.detail', session_id=existing.id))

    code = _generate_session_code()
    sess = ClinicalSession(
        session_code=code,
        patient_id=apt.patient_id,
        dentist_id=apt.dentist_id or current_user.id,
        appointment_id=apt.id,
        session_date=datetime.now(timezone.utc),
        status=SessionStatus.IN_PROGRESS,
        created_by_id=current_user.id,
    )
    db.session.add(sess)
    apt.status = 'in_progress'
    db.session.commit()
    log_action('clinical_sessions', 'CREATE', record_id=sess.id,
               new_value={'session_code': code, 'patient_id': apt.patient_id},
               description=f'Session started from appointment #{appointment_id}')
    flash(_(f'Sessão {code} iniciada.'), 'success')
    return redirect(url_for('sessions.edit', session_id=sess.id))


@sessions_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create a standalone session (not linked to an appointment)."""
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]:
        abort(403)

    form = SessionForm()
    # Populate treatments choices
    form.treatments.choices = [
        (t.id, t.name_pt) for t in Treatment.query.filter_by(is_active=True).order_by(Treatment.name_pt)
    ]
    form.status.choices = [('in_progress', _('Em Progresso')), ('closed', _('Fechar Sessão')), ('cancelled', _('Cancelar'))]

    # Build patient list
    if current_user.role == Role.DENTIST:
        patients = Patient.query.filter_by(assigned_dentist_id=current_user.id, is_active=True).order_by(Patient.full_name).all()
    else:
        patients = Patient.query.filter_by(is_active=True).order_by(Patient.full_name).all()

    if form.validate_on_submit():
        patient_id = request.form.get('patient_id', type=int)
        if not patient_id:
            flash(_('Selecione um paciente.'), 'danger')
            return render_template('sessions/new.html', form=form, patients=patients)
        code = _generate_session_code()
        sess = ClinicalSession(
            session_code=code,
            patient_id=patient_id,
            dentist_id=current_user.id,
            session_date=datetime.now(timezone.utc),
            chief_complaint=form.chief_complaint.data,
            clinical_notes=form.clinical_notes.data,
            diagnosis=form.diagnosis.data,
            treatment_plan=form.treatment_plan.data,
            odontogram_data=json.loads(form.odontogram_data.data) if form.odontogram_data.data else None,
            status=form.status.data,
            bp_systolic=form.bp_systolic.data,
            bp_diastolic=form.bp_diastolic.data,
            heart_rate=form.heart_rate.data,
            temperature=float(form.temperature.data) if form.temperature.data is not None else None,
            weight_kg=float(form.weight_kg.data) if form.weight_kg.data is not None else None,
            oxygen_saturation=form.oxygen_saturation.data,
            created_by_id=current_user.id,
        )
        if form.status.data == 'closed':
            sess.closed_at = datetime.now(timezone.utc)
        db.session.add(sess)
        db.session.flush()
        # Save treatments (apply urgency surcharge if appointment is emergency)
        surcharge_pct = _get_surcharge_pct(sess)
        for tid in form.treatments.data or []:
            t = Treatment.query.get(tid)
            if t:
                final_price, applied_pct = _urgency_price(t.price, surcharge_pct)
                db.session.add(SessionTreatment(
                    session_id=sess.id, treatment_id=tid,
                    price_at_time=final_price,
                    urgency_surcharge_pct=applied_pct
                ))
        db.session.commit()
        log_action('clinical_sessions', 'CREATE', record_id=sess.id,
                   new_value={'session_code': code, 'patient_id': patient_id},
                   description='Manual session created')
        flash(_(f'Sessão {code} criada.'), 'success')
        return redirect(url_for('sessions.detail', session_id=sess.id))

    return render_template('sessions/new.html', form=form, patients=patients)


# ─── SESSION DETAIL (READ-ONLY VIEW) ─────────────────────────────────────────

@sessions_bp.route('/<int:session_id>')
@login_required
def detail(session_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)
    treatments = sess.session_treatments
    prescriptions = sess.prescriptions.all()
    xrays = sess.xrays.all()
    consumables = sess.session_consumables.all()
    can_edit = _can_edit_session(sess)
    can_addendum = (current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]
                    and sess.status == SessionStatus.CLOSED)
    addendum_form = AddendumForm() if can_addendum else None
    return render_template('sessions/detail.html', sess=sess, treatments=treatments,
                           prescriptions=prescriptions, xrays=xrays,
                           consumables=consumables,
                           can_edit=can_edit, can_addendum=can_addendum,
                           addendum_form=addendum_form)


# ─── SESSION EDIT ─────────────────────────────────────────────────────────────

@sessions_bp.route('/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(session_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)

    if sess.status == SessionStatus.CLOSED:
        flash(_('Esta sessão está fechada e não pode ser editada.'), 'warning')
        return redirect(url_for('sessions.detail', session_id=sess.id))

    if not _can_edit_session(sess):
        abort(403)

    form = SessionForm(obj=sess)
    form.treatments.choices = [
        (t.id, t.name_pt) for t in Treatment.query.filter_by(is_active=True).order_by(Treatment.name_pt)
    ]
    form.status.choices = [('in_progress', _('Em Progresso')), ('closed', _('Fechar Sessão')), ('cancelled', _('Cancelar'))]

    all_medicines = Medicine.query.filter_by(is_active=True).order_by(Medicine.name_pt).all()
    presc_form = PrescriptionForm()
    presc_form.medicine_id.choices = [(0, _('Selecionar...'))] + [(m.id, m.name_pt) for m in all_medicines]

    xray_form = XRayUploadForm()

    if request.method == 'GET':
        # Pre-select existing treatments
        form.treatments.data = [st.treatment_id for st in sess.session_treatments]
        # Populate odontogram JSON
        if sess.odontogram_data:
            form.odontogram_data.data = json.dumps(sess.odontogram_data)

    if form.validate_on_submit():
        old_snapshot = {
            'status':          sess.status if isinstance(sess.status, str) else sess.status.value,
            'chief_complaint': sess.chief_complaint,
            'clinical_notes':  sess.clinical_notes,
            'diagnosis':       sess.diagnosis,
            'treatment_plan':  sess.treatment_plan,
            'bp_systolic':     sess.bp_systolic,
            'bp_diastolic':    sess.bp_diastolic,
            'heart_rate':      sess.heart_rate,
        }

        # Route-level early gate: detect changed fields and assert mutability
        field_map = {
            'chief_complaint': form.chief_complaint.data,
            'clinical_notes': form.clinical_notes.data,
            'diagnosis': form.diagnosis.data,
            'treatment_plan': form.treatment_plan.data,
            'bp_systolic': form.bp_systolic.data,
            'bp_diastolic': form.bp_diastolic.data,
            'heart_rate': form.heart_rate.data,
            'temperature': float(form.temperature.data) if form.temperature.data is not None else None,
            'weight_kg': float(form.weight_kg.data) if form.weight_kg.data is not None else None,
            'oxygen_saturation': form.oxygen_saturation.data,
        }
        changed_fields = {f for f, v in field_map.items() if getattr(sess, f) != v}

        try:
            sess.assert_mutable(changed_fields)
        except ImmutableSessionError as e:
            flash(str(e), 'danger')
            return redirect(url_for('sessions.detail', session_id=sess.id))

        sess.chief_complaint = form.chief_complaint.data
        sess.clinical_notes = form.clinical_notes.data
        sess.diagnosis = form.diagnosis.data
        sess.treatment_plan = form.treatment_plan.data
        # Vitals
        sess.bp_systolic = form.bp_systolic.data
        sess.bp_diastolic = form.bp_diastolic.data
        sess.heart_rate = form.heart_rate.data
        sess.temperature = float(form.temperature.data) if form.temperature.data is not None else None
        sess.weight_kg = float(form.weight_kg.data) if form.weight_kg.data is not None else None
        sess.oxygen_saturation = form.oxygen_saturation.data

        # Odontogram
        raw_odo = form.odontogram_data.data
        if raw_odo:
            try:
                sess.odontogram_data = json.loads(raw_odo)
            except (ValueError, TypeError):
                pass

        # Update treatments (clear + re-add, applying urgency surcharge if applicable)
        SessionTreatment.query.filter_by(session_id=sess.id).delete()
        surcharge_pct = _get_surcharge_pct(sess)
        for tid in form.treatments.data or []:
            t = Treatment.query.get(tid)
            if t:
                final_price, applied_pct = _urgency_price(t.price, surcharge_pct)
                db.session.add(SessionTreatment(
                    session_id=sess.id, treatment_id=tid,
                    price_at_time=final_price,
                    urgency_surcharge_pct=applied_pct
                ))

        if form.status.data == 'closed':
            sess.status = SessionStatus.CLOSED
            sess.closed_at = datetime.now(timezone.utc)
            if sess.appointment_id:
                apt = Appointment.query.get(sess.appointment_id)
                if apt:
                    apt.status = 'completed'
        else:
            sess.status = form.status.data

        db.session.commit()
        log_action('clinical_sessions', 'UPDATE', record_id=sess.id,
                   old_value=old_snapshot,
                   description=f'Session edited: {sess.session_code}')

        if sess.status == SessionStatus.CLOSED:
            flash(_('Sessão fechada e imutável.'), 'success')
            return redirect(url_for('sessions.detail', session_id=sess.id))
        flash(_('Sessão guardada.'), 'success')
        return redirect(url_for('sessions.edit', session_id=sess.id))

    prescriptions = sess.prescriptions.all()
    xrays = sess.xrays.all()
    consumables = sess.session_consumables.all()
    stock_products = StockProduct.query.filter_by(is_active=True).order_by(
        StockProduct.category, StockProduct.name_pt).all()
    return render_template('sessions/edit.html', sess=sess, form=form,
                           presc_form=presc_form, xray_form=xray_form,
                           prescriptions=prescriptions, xrays=xrays,
                           consumables=consumables, stock_products=stock_products,
                           all_medicines=all_medicines)


# ─── ADDENDUM (Director only, closed sessions) ────────────────────────────────

@sessions_bp.route('/<int:session_id>/addendum', methods=['POST'])
@login_required
def add_addendum(session_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    sess = ClinicalSession.query.get_or_404(session_id)
    if sess.status != SessionStatus.CLOSED:
        flash(_('Adendas só podem ser adicionadas a sessões fechadas.'), 'warning')
        return redirect(url_for('sessions.detail', session_id=sess.id))

    form = AddendumForm()
    if form.validate_on_submit() and form.addendum_text.data:
        text = form.addendum_text.data.strip()
        # Store addendum as a new linked record — never mutates original session data
        addendum = SessionAddendum(
            session_id=sess.id,
            author_id=current_user.id,
            text=text,
        )
        db.session.add(addendum)
        db.session.commit()
        flash(_('Adenda adicionada com sucesso.'), 'success')
    return redirect(url_for('sessions.detail', session_id=sess.id))


# ─── PRESCRIPTIONS ────────────────────────────────────────────────────────────

@sessions_bp.route('/<int:session_id>/prescriptions/add', methods=['POST'])
@login_required
def add_prescription(session_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)
    if not _can_edit_session(sess):
        abort(403)

    form = PrescriptionForm()
    all_medicines = Medicine.query.filter_by(is_active=True).all()
    form.medicine_id.choices = [(0, '')] + [(m.id, m.name_pt) for m in all_medicines]

    if form.validate_on_submit() and form.medicine_id.data:
        presc = Prescription(
            session_id=sess.id,
            medicine_id=form.medicine_id.data,
            dosage=form.dosage.data,
            frequency=form.frequency.data,
            duration=form.duration.data,
            instructions=form.instructions.data,
        )
        db.session.add(presc)
        db.session.commit()
        log_action('prescriptions', 'CREATE', record_id=presc.id,
                   new_value={'session_id': sess.id, 'medicine_id': form.medicine_id.data},
                   description='Prescription added to session')
        flash(_('Prescrição adicionada.'), 'success')
    return redirect(url_for('sessions.edit', session_id=sess.id))


@sessions_bp.route('/<int:session_id>/prescriptions/<int:presc_id>/delete', methods=['POST'])
@login_required
def delete_prescription(session_id, presc_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)
    if not _can_edit_session(sess):
        abort(403)
    presc = Prescription.query.get_or_404(presc_id)
    if presc.session_id != sess.id:
        abort(404)
    db.session.delete(presc)
    db.session.commit()
    log_action('prescriptions', 'DELETE', record_id=presc_id,
               description='Prescription deleted from session')
    flash(_('Prescrição removida.'), 'info')
    return redirect(url_for('sessions.edit', session_id=sess.id))


# ─── CONSUMABLES ──────────────────────────────────────────────────────────────

@sessions_bp.route('/<int:session_id>/consumables/add', methods=['POST'])
@login_required
def add_consumable(session_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)
    if not _can_edit_session(sess):
        abort(403)
    if current_user.role == Role.PATIENT:
        abort(403)

    product_id = request.form.get('product_id', type=int)
    quantity   = request.form.get('quantity', type=float)
    notes      = request.form.get('notes', '').strip() or None

    if not product_id or not quantity or quantity <= 0:
        flash(_('Produto e quantidade são obrigatórios.'), 'danger')
        return redirect(url_for('sessions.edit', session_id=sess.id))

    product = StockProduct.query.get_or_404(product_id)

    if float(product.qty_current) < quantity:
        flash(_(f'Stock insuficiente. Disponível: {int(product.qty_current)} {product.unit}.'), 'danger')
        return redirect(url_for('sessions.edit', session_id=sess.id))

    # Decrement stock
    product.qty_current = float(product.qty_current) - quantity

    # Create linked StockMovement
    mv = StockMovement(
        product_id    = product.id,
        movement_type = 'out',
        reason        = 'uso',
        quantity      = quantity,
        qty_after     = float(product.qty_current),
        unit_cost     = product.unit_cost,
        session_id    = sess.id,
        notes         = f'Sessão {sess.session_code}',
        created_by_id = current_user.id,
    )
    db.session.add(mv)
    db.session.flush()

    sc = SessionConsumable(
        session_id         = sess.id,
        product_id         = product.id,
        quantity           = quantity,
        unit_cost_snapshot = product.unit_cost,
        notes              = notes,
        created_by_id      = current_user.id,
        stock_movement_id  = mv.id,
    )
    db.session.add(sc)
    db.session.commit()

    log_action('session_consumables', 'CREATE', record_id=sc.id,
               new_value={'product': product.name_pt, 'qty': quantity},
               description=f'Consumable used: {quantity} {product.unit} of {product.name_pt} in {sess.session_code}')
    flash(_(f'Consumível registado: {quantity} {product.unit} de {product.name_pt}.'), 'success')
    return redirect(url_for('sessions.edit', session_id=sess.id))


@sessions_bp.route('/<int:session_id>/consumables/<int:sc_id>/delete', methods=['POST'])
@login_required
def delete_consumable(session_id, sc_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)
    if not _can_edit_session(sess):
        abort(403)
    if current_user.role == Role.PATIENT:
        abort(403)

    sc = SessionConsumable.query.get_or_404(sc_id)
    if sc.session_id != sess.id:
        abort(404)

    # Reverse stock: restore quantity
    product = sc.product
    if product:
        product.qty_current = float(product.qty_current) + float(sc.quantity)

    # Remove linked stock movement
    if sc.stock_movement_id:
        mv = StockMovement.query.get(sc.stock_movement_id)
        if mv:
            db.session.delete(mv)

    db.session.delete(sc)
    db.session.commit()

    log_action('session_consumables', 'DELETE', record_id=sc_id,
               description=f'Consumable removed from session {sess.session_code}')
    flash(_('Consumível removido. Stock reposto.'), 'info')
    return redirect(url_for('sessions.edit', session_id=sess.id))


# ─── X-RAYS ───────────────────────────────────────────────────────────────────

@sessions_bp.route('/<int:session_id>/xrays/upload', methods=['POST'])
@login_required
def upload_xray(session_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)
    if not _can_edit_session(sess):
        abort(403)

    from ..models import AppSetting
    max_mb = int(AppSetting.get('xray_max_mb', 10))
    max_bytes = max_mb * 1024 * 1024
    notes = request.form.get('notes', '')

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        flash(_('Nenhum ficheiro seleccionado.'), 'warning')
        return redirect(url_for('sessions.edit', session_id=sess.id))

    uploaded = 0
    errors = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext not in ALLOWED_XRAY:
            errors.append(_('%(name)s: tipo inválido (use JPG, PNG ou PDF).', name=f.filename))
            continue
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > max_bytes:
            errors.append(_('%(name)s: ficheiro excede o limite de %(mb)d MB.', name=f.filename, mb=max_mb))
            continue
        rel_path = _save_file(f, f'xrays/{sess.session_code}', ALLOWED_XRAY)
        if not rel_path:
            errors.append(_('%(name)s: erro ao guardar ficheiro.', name=f.filename))
            continue
        xray = XRay(
            session_id=sess.id,
            file_path=rel_path,
            file_name=f.filename,
            file_type=ext,
            notes=notes,
            uploaded_by_id=current_user.id,
        )
        db.session.add(xray)
        db.session.flush()
        log_action('xrays', 'CREATE', record_id=xray.id,
                   new_value={'session_code': sess.session_code, 'file': xray.file_name},
                   description='X-Ray uploaded')
        uploaded += 1

    if uploaded:
        db.session.commit()
        flash(_('%(n)d radiografia(s) carregada(s) com sucesso.', n=uploaded), 'success')
    for e in errors:
        flash(e, 'danger')
    return redirect(url_for('sessions.edit', session_id=sess.id))


@sessions_bp.route('/<int:session_id>/xrays/<int:xray_id>/delete', methods=['POST'])
@login_required
def delete_xray(session_id, xray_id):
    sess = ClinicalSession.query.get_or_404(session_id)
    _check_access(sess)
    if not _can_edit_session(sess):
        abort(403)
    xray = XRay.query.get_or_404(xray_id)
    if xray.session_id != sess.id:
        abort(404)
    # Delete physical file
    full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], xray.file_path)
    if os.path.exists(full_path):
        os.remove(full_path)
    db.session.delete(xray)
    db.session.commit()
    log_action('xrays', 'DELETE', record_id=xray_id, description='X-Ray deleted')
    flash(_('Radiografia removida.'), 'info')
    return redirect(url_for('sessions.edit', session_id=sess.id))


# ─── EVOLUTION PHOTOS ─────────────────────────────────────────────────────────

@sessions_bp.route('/patients/<int:patient_id>/gallery')
@login_required
def evolution_gallery(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    _check_patient_access(patient)
    photos = EvolutionPhoto.query.filter_by(patient_id=patient_id).order_by(EvolutionPhoto.uploaded_at).all()
    before = [p for p in photos if p.photo_type == 'before']
    after = [p for p in photos if p.photo_type == 'after']
    form = EvolutionPhotoForm()
    can_upload = current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]
    return render_template('sessions/evolution_gallery.html', patient=patient,
                           photos=photos, before=before, after=after,
                           form=form, can_upload=can_upload)


@sessions_bp.route('/patients/<int:patient_id>/gallery/upload', methods=['POST'])
@login_required
def upload_evolution_photo(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    _check_patient_access(patient)
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]:
        abort(403)

    form = EvolutionPhotoForm()
    if form.validate_on_submit():
        rel_path = _save_file(form.file.data, f'evolution/{patient_id}', ALLOWED_PHOTO)
        if not rel_path:
            flash(_('Tipo de ficheiro inválido. Use JPG ou PNG.'), 'danger')
            return redirect(url_for('sessions.evolution_gallery', patient_id=patient_id))
        photo = EvolutionPhoto(
            patient_id=patient_id,
            photo_type=form.photo_type.data,
            file_path=rel_path,
            caption=form.caption.data,
            uploaded_by_id=current_user.id,
        )
        db.session.add(photo)
        db.session.commit()
        log_action('evolution_photos', 'CREATE', record_id=photo.id,
                   new_value={'patient_id': patient_id, 'type': photo.photo_type},
                   description='Evolution photo uploaded')
        flash(_('Fotografia carregada.'), 'success')
    return redirect(url_for('sessions.evolution_gallery', patient_id=patient_id))


@sessions_bp.route('/patients/<int:patient_id>/gallery/<int:photo_id>/delete', methods=['POST'])
@login_required
def delete_evolution_photo(patient_id, photo_id):
    patient = Patient.query.get_or_404(patient_id)
    _check_patient_access(patient)
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST]:
        abort(403)
    photo = EvolutionPhoto.query.get_or_404(photo_id)
    if photo.patient_id != patient_id:
        abort(404)
    full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.file_path)
    if os.path.exists(full_path):
        os.remove(full_path)
    db.session.delete(photo)
    db.session.commit()
    log_action('evolution_photos', 'DELETE', record_id=photo_id, description='Evolution photo deleted')
    flash(_('Fotografia removida.'), 'info')
    return redirect(url_for('sessions.evolution_gallery', patient_id=patient_id))


# ─── DELETE SESSION ───────────────────────────────────────────────────────────

@sessions_bp.route('/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_session(session_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    sess = ClinicalSession.query.get_or_404(session_id)
    patient_id = sess.patient_id
    code = sess.session_code
    SessionConsumable.query.filter_by(session_id=session_id).delete()
    SessionTreatment.query.filter_by(session_id=session_id).delete()
    Prescription.query.filter_by(session_id=session_id).delete()
    XRay.query.filter_by(session_id=session_id).delete()
    SessionAddendum.query.filter_by(session_id=session_id).delete()
    db.session.delete(sess)
    db.session.commit()
    log_action('clinical_sessions', 'DELETE', record_id=session_id,
               description=f'Session permanently deleted: {code}')
    flash(_('Sessão eliminada permanentemente.'), 'danger')
    return redirect(url_for('patients.detail', patient_id=patient_id))


# ─── AUDIT LOG ────────────────────────────────────────────────────────────────

@sessions_bp.route('/audit')
@login_required
def audit_view():
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    page = request.args.get('page', 1, type=int)
    q = AuditLog.query.order_by(AuditLog.timestamp.desc())

    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    table = request.args.get('table', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    if user_id:
        q = q.filter_by(user_id=user_id)
    if action:
        q = q.filter_by(action=action.upper())
    if table:
        q = q.filter_by(table_name=table)
    if date_from:
        try:
            q = q.filter(AuditLog.timestamp >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(AuditLog.timestamp <= datetime.fromisoformat(date_to + 'T23:59:59'))
        except ValueError:
            pass

    logs = q.paginate(page=page, per_page=50)
    users = User.query.order_by(User.full_name).all()
    tables = db.session.query(AuditLog.table_name).distinct().all()
    tables = [t[0] for t in tables]
    actions = ['CREATE', 'UPDATE', 'DELETE', 'ADDENDUM']
    return render_template('sessions/audit_log.html', logs=logs, users=users,
                           tables=tables, actions=actions,
                           current_user_id=user_id, current_action=action,
                           current_table=table, date_from=date_from, date_to=date_to)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _check_access(sess):
    """Verify the current user may view/edit this session."""
    if current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        return
    if current_user.role == Role.DENTIST:
        if sess.dentist_id == current_user.id:
            return
        abort(403)
    if current_user.role == Role.PATIENT:
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        if patient and patient.id == sess.patient_id:
            return
        abort(403)
    abort(403)


def _check_patient_access(patient):
    """Verify the current user may access this patient's data."""
    if current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.RECEPTION]:
        return
    if current_user.role == Role.DENTIST:
        if patient.assigned_dentist_id == current_user.id:
            return
        abort(403)
    if current_user.role == Role.PATIENT:
        if patient.user_id == current_user.id:
            return
        abort(403)
    abort(403)
