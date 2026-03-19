import os
import logging
import subprocess
from flask import Flask, session, request
from flask_wtf.csrf import CSRFProtect
from .extensions import db, login_manager, babel
from .models import User, Role, RoleDefinition, AppSetting

logger = logging.getLogger(__name__)
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__, instance_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance'))
    os.makedirs(app.instance_path, exist_ok=True)

    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        if os.environ.get('FLASK_ENV') == 'production':
            raise RuntimeError('SECRET_KEY environment variable must be set in production!')
        secret_key = 'dental-dev-key-NOT-for-production-use'
        logger.warning('SECRET_KEY not set — using insecure dev key. Set SECRET_KEY in production!')
    app.config['SECRET_KEY'] = secret_key

    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'dental.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['BABEL_DEFAULT_LOCALE'] = 'pt'
    app.config['BABEL_SUPPORTED_LOCALES'] = ['pt', 'en', 'es']
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'translations')
    app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024  # 512 MB (suporta backup ZIPs grandes)
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    app.config['WTF_CSRF_ENABLED'] = True
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    csrf.init_app(app)

    from .audit_events import register_events
    register_events(db)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, inicie sessão para aceder a esta página.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .auth import auth_bp
    from .admin import admin_bp
    from .main import main_bp
    from .patients import patients_bp
    from .scheduling import scheduling_bp
    from .sessions import sessions_bp
    from .superadmin import superadmin_bp
    from .stock import stock_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(main_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(scheduling_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(superadmin_bp, url_prefix='/superadmin')
    app.register_blueprint(stock_bp)

    from flask_babel import get_locale as babel_get_locale
    app.jinja_env.globals['get_locale'] = babel_get_locale

    @app.context_processor
    def inject_app_settings():
        try:
            settings = AppSetting.all_as_dict()
        except Exception:
            settings = dict(AppSetting._DEFAULTS)
        return {'app_settings': settings}

    with app.app_context():
        db.create_all()
        _migrate_db_columns()
        RoleDefinition.seed()
        _seed_initial_data()
        _seed_rooms()
        _compile_translations_if_needed(app)

    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('404.html'), 404

    return app


def get_locale():
    lang = session.get('lang')
    if lang in ['pt', 'en', 'es']:
        return lang
    return 'pt'


def _seed_initial_data():
    from werkzeug.security import generate_password_hash

    seed_demo = os.environ.get('SEED_DEMO_USERS', '').lower() in ('1', 'true', 'yes')

    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            email='admin@clinic.local',
            full_name='Administrator',
            role=Role.SUPERADMIN,
            password_hash=generate_password_hash('admin', method='pbkdf2:sha256'),
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        logger.info('Seeded default admin account')

    if seed_demo:
        demo_users = [
            dict(username='director', email='director@clinic.local', full_name='Clinical Director',
                 role=Role.CLINICAL_DIRECTOR, password='changeme123'),
            dict(username='dentist1', email='dentist1@clinic.local', full_name='Dr. Maria Silva',
                 role=Role.DENTIST, password='changeme123'),
            dict(username='reception', email='reception@clinic.local', full_name='Ana Recepção',
                 role=Role.RECEPTION, password='changeme123'),
            dict(username='patient1', email='patient1@clinic.local', full_name='João Paciente',
                 role=Role.PATIENT, password='changeme123'),
        ]
        created = 0
        for u in demo_users:
            if not User.query.filter_by(username=u['username']).first():
                user = User(
                    username=u['username'],
                    email=u['email'],
                    full_name=u['full_name'],
                    role=u['role'],
                    password_hash=generate_password_hash(u['password'], method='pbkdf2:sha256'),
                    is_active=True
                )
                db.session.add(user)
                created += 1
        if created:
            db.session.commit()
            logger.info('Seeded %d demo users (SEED_DEMO_USERS=1)', created)


def _migrate_db_columns():
    """Idempotent: add new columns to existing tables without dropping data."""
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    with db.engine.connect() as conn:
        # Chronic conditions fields on patients
        try:
            existing = [c['name'] for c in inspector.get_columns('patients')]
        except Exception:
            existing = []
        new_cols = {
            'chronic_conditions_pt': 'TEXT',
            'chronic_conditions_en': 'TEXT',
            'chronic_conditions_es': 'TEXT',
        }
        for col, coltype in new_cols.items():
            if col not in existing:
                try:
                    conn.execute(text(f'ALTER TABLE patients ADD COLUMN {col} {coltype}'))
                    conn.commit()
                    logger.info('Migration: added column patients.%s', col)
                except Exception as e:
                    logger.warning('Migration skip %s: %s', col, e)

        # clinical_sessions new columns
        try:
            cs_existing = [c['name'] for c in inspector.get_columns('clinical_sessions')]
        except Exception:
            cs_existing = []
        cs_cols = {
            'created_by_id': 'INTEGER',
            'bp_systolic': 'INTEGER',
            'bp_diastolic': 'INTEGER',
            'heart_rate': 'INTEGER',
            'temperature': 'REAL',
            'weight_kg': 'REAL',
            'oxygen_saturation': 'INTEGER',
        }
        for col, coltype in cs_cols.items():
            if col not in cs_existing:
                try:
                    conn.execute(text(f'ALTER TABLE clinical_sessions ADD COLUMN {col} {coltype}'))
                    conn.commit()
                    logger.info('Migration: added column clinical_sessions.%s', col)
                except Exception as e:
                    logger.warning('Migration skip clinical_sessions.%s: %s', col, e)

        # stock_movements new columns
        try:
            sm_existing = [c['name'] for c in inspector.get_columns('stock_movements')]
        except Exception:
            sm_existing = []
        for col, coltype in {'invoice_file_path': 'VARCHAR(500)', 'invoice_file_name': 'VARCHAR(255)'}.items():
            if col not in sm_existing:
                try:
                    conn.execute(text(f'ALTER TABLE stock_movements ADD COLUMN {col} {coltype}'))
                    conn.commit()
                    logger.info('Migration: added column stock_movements.%s', col)
                except Exception as e:
                    logger.warning('Migration skip stock_movements.%s: %s', col, e)

        # session_treatments new columns
        try:
            st_existing = [c['name'] for c in inspector.get_columns('session_treatments')]
        except Exception:
            st_existing = []
        if 'urgency_surcharge_pct' not in st_existing:
            try:
                conn.execute(text('ALTER TABLE session_treatments ADD COLUMN urgency_surcharge_pct REAL'))
                conn.commit()
                logger.info('Migration: added column session_treatments.urgency_surcharge_pct')
            except Exception as e:
                logger.warning('Migration skip session_treatments.urgency_surcharge_pct: %s', e)

        # patient_care_team table (multi-dentist access)
        try:
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS patient_care_team (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                    dentist_id INTEGER NOT NULL REFERENCES users(id),
                    requested_by_id INTEGER NOT NULL REFERENCES users(id),
                    approved_by_id INTEGER REFERENCES users(id),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    notes TEXT,
                    created_at DATETIME,
                    resolved_at DATETIME
                )
            '''))
            conn.commit()
            logger.info('Migration: ensured patient_care_team table')
        except Exception as e:
            logger.warning('Migration patient_care_team: %s', e)


def _seed_rooms():
    from .models import Room, RoomStatus
    if not Room.query.first():
        for num, name in [(1, 'Consultório 1'), (2, 'Consultório 2')]:
            db.session.add(Room(name=name, number=num, status=RoomStatus.GREEN))
        db.session.commit()
        logger.info('Seeded 2 rooms')


def _compile_translations_if_needed(app):
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'translations')
    import shutil
    pybabel_candidates = [
        'pybabel',
        '/home/runner/workspace/.pythonlibs/bin/pybabel',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                     '..', '..', '.pythonlibs', 'bin', 'pybabel'),
    ]
    pybabel = next((c for c in pybabel_candidates if shutil.which(c) or os.path.isfile(c)), None)

    for lang in ['pt', 'en', 'es']:
        mo_path = os.path.join(base, lang, 'LC_MESSAGES', 'messages.mo')
        po_path = os.path.join(base, lang, 'LC_MESSAGES', 'messages.po')
        if os.path.exists(po_path) and not os.path.exists(mo_path):
            if pybabel:
                try:
                    result = subprocess.run(
                        [pybabel, 'compile', '-f', '-i', po_path, '-o', mo_path],
                        capture_output=True, text=True, check=True
                    )
                    logger.info('Compiled translations for %s', lang)
                except subprocess.CalledProcessError as exc:
                    logger.error('pybabel compile failed for %s: %s', lang, exc.stderr)
            else:
                logger.warning('pybabel not found — %s translations will not be compiled', lang)
