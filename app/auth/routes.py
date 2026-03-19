from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from flask_babel import gettext as _

from . import auth_bp
from .forms import LoginForm, ChangePasswordForm
from ..models import User
from ..extensions import db
from ..audit import log_action


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            if not user.is_active:
                flash(_('Conta desativada. Contacte o administrador.'), 'danger')
                return render_template('auth/login.html', form=form)
            login_user(user, remember=form.remember_me.data)
            log_action('users', 'LOGIN', record_id=user.id, description=f'User {user.username} logged in')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        flash(_('Utilizador ou senha inválidos.'), 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    log_action('users', 'LOGOUT', record_id=current_user.id,
               description=f'User {current_user.username} logged out')
    logout_user()
    flash(_('Sessão encerrada com sucesso.'), 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    import os
    from flask import current_app, request as flask_request
    from werkzeug.utils import secure_filename
    from PIL import Image as PILImage

    form = ChangePasswordForm()

    # Handle signature upload (any form submit with a signature file)
    sig_file = flask_request.files.get('signature_file')
    if sig_file and sig_file.filename:
        upload_folder = current_app.config['UPLOAD_FOLDER']
        sig_dir = os.path.join(upload_folder, 'signatures')
        os.makedirs(sig_dir, exist_ok=True)
        ext = os.path.splitext(sig_file.filename)[1].lower()
        if ext not in ['.png', '.jpg', '.jpeg']:
            flash(_('Apenas imagens PNG/JPG são aceites para assinatura.'), 'danger')
        else:
            filename = f"{current_user.id}.png"
            dest = os.path.join(sig_dir, filename)
            try:
                img = PILImage.open(sig_file.stream).convert('RGBA')
                img.thumbnail((400, 120))
                img.save(dest, 'PNG')
                current_user.signature_path = f'signatures/{filename}'
                db.session.commit()
                log_action('users', 'UPDATE', record_id=current_user.id,
                           description='Digital signature uploaded')
                flash(_('Assinatura digital actualizada com sucesso!'), 'success')
            except Exception as e:
                flash(_('Erro ao processar imagem:') + f' {str(e)}', 'danger')
        return redirect(url_for('auth.profile'))

    if form.validate_on_submit():
        if check_password_hash(current_user.password_hash, form.current_password.data):
            current_user.password_hash = generate_password_hash(
                form.new_password.data, method='pbkdf2:sha256'
            )
            db.session.commit()
            log_action('users', 'UPDATE', record_id=current_user.id,
                       description='Password changed')
            flash(_('Senha alterada com sucesso!'), 'success')
            return redirect(url_for('auth.profile'))
        flash(_('Senha atual incorreta.'), 'danger')

    return render_template('auth/profile.html', form=form)


@auth_bp.route('/set-lang/<lang>')
def set_lang(lang):
    if lang in ['pt', 'en', 'es']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('main.dashboard'))


@auth_bp.route('/toggle-theme')
@login_required
def toggle_theme():
    current_theme = session.get('theme', 'dark')
    session['theme'] = 'light' if current_theme == 'dark' else 'dark'
    return redirect(request.referrer or url_for('main.dashboard'))
