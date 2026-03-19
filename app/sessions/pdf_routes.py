"""PDF download routes — RBAC-guarded, trilingual."""
import os
from flask import Response, abort, request, current_app
from flask_login import login_required, current_user
from flask_babel import get_locale

from . import sessions_bp
from ..models import Role, ClinicalSession, Patient


def _get_session_or_403(session_id):
    """Load a session and verify the current user may access it."""
    sess = ClinicalSession.query.get_or_404(session_id)
    role = current_user.role

    if role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        return sess  # full access

    if role == Role.DENTIST:
        if sess.dentist_id != current_user.id:
            abort(403)
        return sess

    if role == Role.PATIENT:
        patient = Patient.query.filter_by(user_id=current_user.id).first()
        if not patient or sess.patient_id != patient.id:
            abort(403)
        return sess

    abort(403)


@sessions_bp.route('/<int:session_id>/pdf/treatment-plan')
@login_required
def pdf_treatment_plan(session_id):
    sess = _get_session_or_403(session_id)
    locale = request.args.get('lang', str(get_locale()) or 'pt')
    if locale not in ['pt', 'en', 'es']:
        locale = 'pt'

    from ..pdfs import generate_treatment_plan_pdf
    pdf_bytes = generate_treatment_plan_pdf(
        sess, locale=locale,
        upload_folder=current_app.config['UPLOAD_FOLDER']
    )
    filename = f"plano-tratamento-{sess.session_code}-{locale}.pdf"
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@sessions_bp.route('/<int:session_id>/pdf/consent-form')
@login_required
def pdf_consent_form(session_id):
    sess = _get_session_or_403(session_id)
    locale = request.args.get('lang', str(get_locale()) or 'pt')
    if locale not in ['pt', 'en', 'es']:
        locale = 'pt'

    from ..pdfs import generate_consent_form_pdf
    pdf_bytes = generate_consent_form_pdf(
        sess, locale=locale,
        upload_folder=current_app.config['UPLOAD_FOLDER']
    )
    filename = f"consentimento-{sess.session_code}-{locale}.pdf"
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@sessions_bp.route('/<int:session_id>/pdf/prescription')
@login_required
def pdf_prescription(session_id):
    sess = _get_session_or_403(session_id)
    locale = request.args.get('lang', str(get_locale()) or 'pt')
    if locale not in ['pt', 'en', 'es']:
        locale = 'pt'

    from ..pdfs import generate_prescription_pdf
    pdf_bytes = generate_prescription_pdf(
        sess, locale=locale,
        upload_folder=current_app.config['UPLOAD_FOLDER']
    )
    filename = f"receita-{sess.session_code}-{locale}.pdf"
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
