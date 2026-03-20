"""Superadmin panel: server monitoring, GitHub sync, SMB backup/restore."""
import os
import io
import shutil
import subprocess
import json
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

from flask import render_template, redirect, url_for, flash, request, Response, stream_with_context, current_app, send_from_directory
from flask_login import login_required, current_user
from flask_babel import gettext as _

from . import superadmin_bp
from ..decorators import superadmin_required
from ..models import Role, AppSetting, RoleDefinition, User
from ..extensions import db

LOGO_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads', 'logos')
ALLOWED_IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}

def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTS


# ──────────────────────────────────────────────────────────────────────────────
# Panel index
# ──────────────────────────────────────────────────────────────────────────────

@superadmin_bp.route('/')
@login_required
@superadmin_required
def index():
    smb_cfg = _load_smb_config()
    git_config = _load_git_config()
    return render_template('superadmin/index.html', smb_cfg=smb_cfg, git_config=git_config)


# ──────────────────────────────────────────────────────────────────────────────
# System Settings
# ──────────────────────────────────────────────────────────────────────────────

@superadmin_bp.route('/system', methods=['GET', 'POST'])
@login_required
@superadmin_required
def system_settings():
    if request.method == 'POST':
        app_name = request.form.get('app_name', '').strip()
        if app_name:
            AppSetting.set('app_name', app_name)

        color_keys = [
            'bg_dark', 'sidebar_dark', 'card_dark', 'border_dark', 'text_dark',
            'primary_dark', 'success_dark', 'danger_dark', 'warning_dark',
            'bg_light', 'card_light', 'border_light', 'text_light',
            'primary_light', 'success_light', 'danger_light', 'warning_light',
        ]
        for key in color_keys:
            val = request.form.get(key, '').strip()
            if val and val.startswith('#') and len(val) == 7:
                AppSetting.set(key, val)

        xray_mb = request.form.get('xray_max_mb', '').strip()
        if xray_mb.isdigit() and 1 <= int(xray_mb) <= 200:
            AppSetting.set('xray_max_mb', xray_mb)

        invoice_mb = request.form.get('stock_invoice_max_mb', '').strip()
        if invoice_mb.isdigit() and 1 <= int(invoice_mb) <= 200:
            AppSetting.set('stock_invoice_max_mb', invoice_mb)

        urgency = request.form.get('urgency_surcharge', '').strip()
        if urgency.isdigit() and 0 <= int(urgency) <= 500:
            AppSetting.set('urgency_surcharge', urgency)

        logo = request.files.get('app_logo')
        if logo and logo.filename and _allowed_image(logo.filename):
            os.makedirs(LOGO_FOLDER, exist_ok=True)
            filename = secure_filename(logo.filename)
            logo.save(os.path.join(LOGO_FOLDER, filename))
            AppSetting.set('app_logo', filename)

        if request.form.get('remove_logo'):
            AppSetting.set('app_logo', '')

        for key in ('app_clinic_name', 'app_subtitle', 'app_nif',
                    'app_phone', 'app_email', 'app_address'):
            val = request.form.get(key, '').strip()
            AppSetting.set(key, val)

        flash(_('Configurações guardadas com sucesso.'), 'success')
        return redirect(url_for('superadmin.system_settings'))

    settings = AppSetting.all_as_dict()
    return render_template('superadmin/system.html', settings=settings)


@superadmin_bp.route('/logos/<path:filename>')
@login_required
def logo_file(filename):
    return send_from_directory(LOGO_FOLDER, filename)


# ──────────────────────────────────────────────────────────────────────────────
# Server metrics API (JSON) — polled every 10 s by the page
# ──────────────────────────────────────────────────────────────────────────────

@superadmin_bp.route('/api/metrics')
@login_required
@superadmin_required
def api_metrics():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        boot = datetime.fromtimestamp(psutil.boot_time()).strftime('%d/%m/%Y %H:%M')

        # Network I/O
        net = psutil.net_io_counters()
        net_sent = _human_bytes(net.bytes_sent)
        net_recv = _human_bytes(net.bytes_recv)

        data = {
            'cpu_pct': cpu,
            'ram_pct': mem.percent,
            'ram_used': _human_bytes(mem.used),
            'ram_total': _human_bytes(mem.total),
            'disk_pct': disk.percent,
            'disk_used': _human_bytes(disk.used),
            'disk_total': _human_bytes(disk.total),
            'boot_time': boot,
            'net_sent': net_sent,
            'net_recv': net_recv,
        }
    except ImportError:
        data = {'error': 'psutil not installed'}
    return Response(json.dumps(data), mimetype='application/json')


def _human_bytes(n):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


# ──────────────────────────────────────────────────────────────────────────────
# GitHub Sync (git pull)
# ──────────────────────────────────────────────────────────────────────────────

def _load_git_config():
    try:
        config = AppSetting.query.filter_by(key='git_repo_url').first()
        return {'url': config.value} if config else {}
    except Exception:
        return {}

@superadmin_bp.route('/git-config-save', methods=['POST'])
@login_required
@superadmin_required
def git_config_save():
    github_url = request.form.get('github_url', '').strip()
    if github_url:
        AppSetting.set('git_repo_url', github_url)
        flash(_('URL do repositório salvo com sucesso.'), 'success')
    else:
        AppSetting.set('git_repo_url', '')
        flash(_('URL removido.'), 'info')
    return redirect(url_for('superadmin.index'))

@superadmin_bp.route('/git-pull', methods=['GET', 'POST'])
@login_required
@superadmin_required
def git_pull():
    """Stream git pull output via Server-Sent Events."""
    repo_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', '..', '..', '..'))

    def _generate():
        try:
            git_cfg = _load_git_config()
            repo_url = git_cfg.get('url', '')
            
            if repo_url:
                yield f"data: [INFO] Configurando remoto para: {repo_url}\n\n"
                set_remote = subprocess.run(
                    ['git', 'remote', 'set-url', 'origin', repo_url],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if set_remote.returncode != 0:
                    yield f"data: [WARN] Erro ao configurar remoto: {set_remote.stderr}\n\n"
            
            proc = subprocess.Popen(
                ['git', 'pull'],
                cwd=repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            for line in proc.stdout:
                yield f"data: {line.rstrip()}\n\n"
            proc.wait(timeout=60)
            rc = proc.returncode
            if rc == 0:
                yield "data: [SUCCESS] git pull concluído.\n\n"
            else:
                yield f"data: [ERROR] git pull falhou (código {rc}).\n\n"
        except FileNotFoundError:
            yield "data: [ERROR] git não encontrado no PATH do servidor.\n\n"
        except subprocess.TimeoutExpired:
            proc.kill()
            yield "data: [ERROR] git pull expirou (timeout 60 s).\n\n"
        except Exception as e:
            yield f"data: [ERROR] {e}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(_generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# SMB Backup / Restore
# ──────────────────────────────────────────────────────────────────────────────

def _smb_config_path():
    instance = current_app.instance_path
    return os.path.join(instance, 'smb_config.json')


def _load_smb_config():
    p = _smb_config_path()
    if os.path.isfile(p):
        with open(p) as f:
            return json.load(f)
    return {}


def _save_smb_config(cfg):
    with open(_smb_config_path(), 'w') as f:
        json.dump(cfg, f)


@superadmin_bp.route('/smb-config', methods=['POST'])
@login_required
@superadmin_required
def smb_config_save():
    cfg = {
        'host': request.form.get('smb_host', '').strip(),
        'share': request.form.get('smb_share', '').strip(),
        'username': request.form.get('smb_username', '').strip(),
        'password': request.form.get('smb_password', '').strip(),
        'remote_path': request.form.get('smb_remote_path', 'dental_backup').strip(),
    }
    _save_smb_config(cfg)
    flash(_('Configuração SMB guardada.'), 'success')
    return redirect(url_for('superadmin.index'))


@superadmin_bp.route('/backup', methods=['POST'])
@login_required
@superadmin_required
def backup():
    """Copy DB + uploads to SMB share using pysmb."""
    cfg = _load_smb_config()
    if not cfg.get('host'):
        flash(_('Configure o servidor SMB antes de efectuar backup.'), 'warning')
        return redirect(url_for('superadmin.index'))

    try:
        from smb.SMBConnection import SMBConnection

        db_path = os.path.join(current_app.instance_path, 'dental.db')
        upload_folder = current_app.config['UPLOAD_FOLDER']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        remote_base = cfg.get('remote_path', 'dental_backup')

        conn = SMBConnection(
            cfg['username'], cfg['password'],
            'dentalcare-client', cfg['host'],
            use_ntlm_v2=True
        )
        assert conn.connect(cfg['host'], 139, timeout=10)

        # Upload DB
        remote_db = f"{remote_base}/dental_{timestamp}.db"
        with open(db_path, 'rb') as f:
            conn.storeFile(cfg['share'], remote_db, f)

        # Upload uploads folder as a tar-gz in memory
        tar_buf = io.BytesIO()
        import tarfile
        with tarfile.open(fileobj=tar_buf, mode='w:gz') as tar:
            tar.add(upload_folder, arcname='uploads')
        tar_buf.seek(0)
        remote_tar = f"{remote_base}/uploads_{timestamp}.tar.gz"
        conn.storeFile(cfg['share'], remote_tar, tar_buf)

        conn.close()
        flash(_('Backup enviado para SMB com sucesso:') + f' {remote_db}', 'success')
    except ImportError:
        flash(_('pysmb não instalado.'), 'danger')
    except Exception as e:
        flash(_('Erro no backup SMB:') + f' {str(e)}', 'danger')

    return redirect(url_for('superadmin.index'))


@superadmin_bp.route('/restore', methods=['POST'])
@login_required
@superadmin_required
def restore():
    """Restore most recent DB + uploads backup from SMB share."""
    cfg = _load_smb_config()
    if not cfg.get('host'):
        flash(_('Configure o servidor SMB antes de restaurar.'), 'warning')
        return redirect(url_for('superadmin.index'))

    try:
        import tarfile
        from smb.SMBConnection import SMBConnection

        db_path = os.path.join(current_app.instance_path, 'dental.db')
        upload_folder = current_app.config['UPLOAD_FOLDER']
        remote_base = cfg.get('remote_path', 'dental_backup')

        conn = SMBConnection(
            cfg['username'], cfg['password'],
            'dentalcare-client', cfg['host'],
            use_ntlm_v2=True
        )
        assert conn.connect(cfg['host'], 139, timeout=10)

        files = conn.listPath(cfg['share'], remote_base)
        names = [f.filename for f in files if not f.filename.startswith('.')]

        # Find most recent .db file
        db_files = sorted([n for n in names if n.endswith('.db')], reverse=True)
        if not db_files:
            flash(_('Nenhum backup encontrado no SMB.'), 'warning')
            conn.close()
            return redirect(url_for('superadmin.index'))

        latest_db = db_files[0]
        remote_db = f"{remote_base}/{latest_db}"

        # Download DB to temp then replace
        tmp_db = db_path + '.tmp'
        with open(tmp_db, 'wb') as f:
            conn.retrieveFile(cfg['share'], remote_db, f)
        shutil.move(tmp_db, db_path)

        # Derive matching uploads tarball (same timestamp prefix)
        # e.g. dental_20240315_120000.db → uploads_20240315_120000.tar.gz
        ts_part = latest_db.replace('dental_', '').replace('.db', '')
        matching_tar = f'uploads_{ts_part}.tar.gz'

        restored_uploads = False
        if matching_tar in names:
            tar_remote = f"{remote_base}/{matching_tar}"
        else:
            # Fall back to most recent uploads tarball
            tar_files = sorted([n for n in names if n.startswith('uploads_') and n.endswith('.tar.gz')], reverse=True)
            tar_remote = f"{remote_base}/{tar_files[0]}" if tar_files else None
            matching_tar = tar_files[0] if tar_files else None

        if tar_remote and matching_tar:
            tar_buf = io.BytesIO()
            conn.retrieveFile(cfg['share'], tar_remote, tar_buf)
            tar_buf.seek(0)
            with tarfile.open(fileobj=tar_buf, mode='r:gz') as tar:
                # Extract safely: strip leading 'uploads/' prefix, land in upload_folder
                parent = os.path.dirname(upload_folder.rstrip('/'))
                for member in tar.getmembers():
                    # Security: prevent path traversal
                    member_path = os.path.realpath(os.path.join(parent, member.name))
                    if not member_path.startswith(os.path.realpath(parent)):
                        continue
                    tar.extract(member, path=parent)
            restored_uploads = True

        conn.close()
        msg = _('Base de dados restaurada a partir de: ') + latest_db
        if restored_uploads:
            msg += '. ' + _('Uploads restaurados a partir de: ') + matching_tar
        flash(msg, 'success')
    except ImportError:
        flash(_('pysmb não instalado.'), 'danger')
    except Exception as e:
        flash(_('Erro na restauração SMB:') + f' {str(e)}', 'danger')

    return redirect(url_for('superadmin.index'))


# ──────────────────────────────────────────────────────────────────────────────
# Local Browser Backup / Restore
# ──────────────────────────────────────────────────────────────────────────────

@superadmin_bp.route('/local-backup')
@login_required
@superadmin_required
def local_backup():
    """Create a ZIP (DB + uploads) and stream it to the browser as a download."""
    import zipfile
    db_path = os.path.join(current_app.instance_path, 'dental.db')
    upload_folder = current_app.config['UPLOAD_FOLDER']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'dental_backup_{timestamp}.zip'

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add the SQLite database
        if os.path.isfile(db_path):
            zf.write(db_path, 'dental.db')
        # Add the uploads folder tree
        if os.path.isdir(upload_folder):
            for root, _dirs, files in os.walk(upload_folder):
                for fname in files:
                    full_path = os.path.join(root, fname)
                    arcname = os.path.join('uploads', os.path.relpath(full_path, upload_folder))
                    zf.write(full_path, arcname)
    buf.seek(0)

    return Response(
        buf.read(),
        mimetype='application/zip',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': 'application/zip',
        }
    )


@superadmin_bp.route('/local-restore', methods=['POST'])
@login_required
@superadmin_required
def local_restore():
    """Restore DB + uploads from an uploaded ZIP file."""
    import zipfile
    f = request.files.get('backup_file')
    if not f or not f.filename.lower().endswith('.zip'):
        flash(_('Seleccione um ficheiro .zip de backup válido.'), 'danger')
        return redirect(url_for('superadmin.index'))

    db_path = os.path.join(current_app.instance_path, 'dental.db')
    upload_folder = current_app.config['UPLOAD_FOLDER']

    try:
        data = io.BytesIO(f.read())
        with zipfile.ZipFile(data, 'r') as zf:
            names = zf.namelist()

            # Restore database
            if 'dental.db' in names:
                with zf.open('dental.db') as src:
                    db_bytes = src.read()
                # Write atomically
                tmp_path = db_path + '.tmp'
                with open(tmp_path, 'wb') as out:
                    out.write(db_bytes)
                os.replace(tmp_path, db_path)
                restored_db = True
            else:
                restored_db = False

            # Restore uploads (only entries starting with 'uploads/')
            upload_entries = [n for n in names if n.startswith('uploads/') and not n.endswith('/')]
            upload_real = os.path.realpath(upload_folder)
            for entry in upload_entries:
                rel = entry[len('uploads/'):]   # strip leading 'uploads/'
                dest = os.path.realpath(os.path.join(upload_folder, rel))
                # Security: prevent path traversal outside upload_folder
                if not dest.startswith(upload_real + os.sep):
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(entry) as src, open(dest, 'wb') as out:
                    out.write(src.read())

        parts = []
        if restored_db:
            parts.append(_('Base de dados restaurada com sucesso.'))
        if upload_entries:
            parts.append(_('%(n)d ficheiros de uploads restaurados.', n=len(upload_entries)))
        flash(' '.join(parts) if parts else _('ZIP vazio — nada restaurado.'),
              'success' if parts else 'warning')
    except Exception as e:
        flash(_('Erro na restauração local: ') + str(e), 'danger')

    return redirect(url_for('superadmin.index'))


# ──────────────────────────────────────────────────────────────────────────────
# Role Definitions CRUD
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_ROLES = {'superadmin', 'clinical_director', 'dentist', 'reception', 'patient'}


@superadmin_bp.route('/roles')
@login_required
@superadmin_required
def roles_index():
    roles = RoleDefinition.query.order_by(RoleDefinition.id).all()
    return render_template('superadmin/roles/index.html', roles=roles)


@superadmin_bp.route('/roles/new', methods=['GET', 'POST'])
@login_required
@superadmin_required
def roles_new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip().lower()
        if not name or not name.replace('_', '').isalnum():
            flash(_('Nome interno inválido.'), 'danger')
            return redirect(url_for('superadmin.roles_new'))
        if RoleDefinition.query.filter_by(name=name).first():
            flash(_('Já existe um perfil com esse nome.'), 'danger')
            return redirect(url_for('superadmin.roles_new'))
        perms = ','.join(p for p in request.form.getlist('permissions') if p)
        rd = RoleDefinition(
            name            = name,
            display_name_pt = request.form.get('display_name_pt', '').strip() or name,
            display_name_en = request.form.get('display_name_en', '').strip() or name,
            display_name_es = request.form.get('display_name_es', '').strip() or name,
            description     = request.form.get('description', '').strip() or None,
            permissions     = perms or None,
        )
        db.session.add(rd)
        db.session.commit()
        flash(_('Perfil criado com sucesso.'), 'success')
        return redirect(url_for('superadmin.roles_index'))
    return render_template('superadmin/roles/form.html', role=None, title=_('Novo Perfil'))


@superadmin_bp.route('/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def roles_edit(role_id):
    rd = RoleDefinition.query.get_or_404(role_id)
    if request.method == 'POST':
        rd.display_name_pt = request.form.get('display_name_pt', '').strip() or rd.display_name_pt
        rd.display_name_en = request.form.get('display_name_en', '').strip() or rd.display_name_en
        rd.display_name_es = request.form.get('display_name_es', '').strip() or rd.display_name_es
        rd.description     = request.form.get('description', '').strip() or None
        perms = ','.join(p for p in request.form.getlist('permissions') if p)
        rd.permissions = perms or None
        db.session.commit()
        flash(_('Perfil actualizado com sucesso.'), 'success')
        return redirect(url_for('superadmin.roles_index'))
    return render_template('superadmin/roles/form.html', role=rd, title=_('Editar Perfil'))


@superadmin_bp.route('/roles/<int:role_id>/delete', methods=['POST'])
@login_required
@superadmin_required
def roles_delete(role_id):
    rd = RoleDefinition.query.get_or_404(role_id)
    if rd.name in SYSTEM_ROLES:
        flash(_('Os perfis de sistema não podem ser eliminados.'), 'danger')
        return redirect(url_for('superadmin.roles_index'))
    db.session.delete(rd)
    db.session.commit()
    flash(_('Perfil eliminado.'), 'success')
    return redirect(url_for('superadmin.roles_index'))
