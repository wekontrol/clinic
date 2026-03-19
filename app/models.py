from datetime import datetime, timezone
from flask_login import UserMixin
from .extensions import db
import enum


class Role(str, enum.Enum):
    SUPERADMIN = 'superadmin'
    CLINICAL_DIRECTOR = 'clinical_director'
    DENTIST = 'dentist'
    PATIENT = 'patient'
    RECEPTION = 'reception'


class RoleDefinition(db.Model):
    """Persistent role catalogue — one row per RBAC role."""
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False, index=True)
    display_name_pt = db.Column(db.String(100), nullable=False)
    display_name_en = db.Column(db.String(100), nullable=False)
    display_name_es = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    permissions = db.Column(db.Text, nullable=True)

    users = db.relationship('User', back_populates='role_definition',
                             foreign_keys='User.role',
                             primaryjoin='User.role == RoleDefinition.name',
                             lazy='dynamic')

    def __repr__(self):
        return f'<RoleDefinition {self.name}>'

    @staticmethod
    def seed():
        """Insert the 5 canonical roles if the table is empty."""
        if RoleDefinition.query.count():
            return
        defaults = [
            dict(name='superadmin',
                 display_name_pt='Superadministrador',
                 display_name_en='Superadmin',
                 display_name_es='Superadministrador',
                 description='Acesso total ao sistema, incluindo painel de sistema e backups.',
                 permissions='all'),
            dict(name='clinical_director',
                 display_name_pt='Diretor Clínico',
                 display_name_en='Clinical Director',
                 display_name_es='Director Clínico',
                 description='Gestão clínica, utilizadores, auditoria e relatórios.',
                 permissions='clinical,users,audit,reports'),
            dict(name='dentist',
                 display_name_pt='Dentista',
                 display_name_en='Dentist',
                 display_name_es='Dentista',
                 description='Gestão de sessões clínicas, odontograma e prescrições.',
                 permissions='clinical,prescriptions,xray'),
            dict(name='reception',
                 display_name_pt='Recepção',
                 display_name_en='Receptionist',
                 display_name_es='Recepción',
                 description='Agendamento de consultas e gestão de pacientes.',
                 permissions='appointments,patients'),
            dict(name='patient',
                 display_name_pt='Paciente',
                 display_name_en='Patient',
                 display_name_es='Paciente',
                 description='Portal de acesso pessoal aos seus dados clínicos.',
                 permissions='own_data'),
        ]
        for rd in defaults:
            db.session.add(RoleDefinition(**rd))
        db.session.commit()


class RoomStatus(str, enum.Enum):
    GREEN = 'green'
    YELLOW = 'yellow'
    RED = 'red'


class SessionStatus(str, enum.Enum):
    SCHEDULED = 'scheduled'
    IN_PROGRESS = 'in_progress'
    CLOSED = 'closed'
    CANCELLED = 'cancelled'


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(30), nullable=False, default=Role.PATIENT)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    signature_path = db.Column(db.String(500), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    specialty = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    sessions_as_dentist = db.relationship('ClinicalSession', foreign_keys='ClinicalSession.dentist_id',
                                           backref='dentist', lazy='dynamic')
    appointments_as_dentist = db.relationship('Appointment', foreign_keys='Appointment.dentist_id',
                                               backref='dentist', lazy='dynamic')
    role_definition = db.relationship('RoleDefinition',
                                       primaryjoin='User.role == RoleDefinition.name',
                                       foreign_keys='User.role',
                                       back_populates='users', lazy='select', uselist=False,
                                       viewonly=True)

    def get_id(self):
        return str(self.id)

    def has_role(self, *roles):
        return self.role in [r.value if isinstance(r, Role) else r for r in roles]

    def is_superadmin(self):
        return self.role == Role.SUPERADMIN

    def is_clinical_director(self):
        return self.role == Role.CLINICAL_DIRECTOR

    def is_dentist(self):
        return self.role == Role.DENTIST

    def is_patient(self):
        return self.role == Role.PATIENT

    def is_reception(self):
        return self.role == Role.RECEPTION

    def role_display(self):
        role_map = {
            Role.SUPERADMIN: 'Superadmin',
            Role.CLINICAL_DIRECTOR: 'Diretor Clínico',
            Role.DENTIST: 'Dentista',
            Role.PATIENT: 'Paciente',
            Role.RECEPTION: 'Recepção',
        }
        return role_map.get(self.role, self.role)

    def role_badge_class(self):
        badge_map = {
            Role.SUPERADMIN: 'danger',
            Role.CLINICAL_DIRECTOR: 'primary',
            Role.DENTIST: 'success',
            Role.PATIENT: 'info',
            Role.RECEPTION: 'warning',
        }
        return badge_map.get(self.role, 'secondary')


class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    full_name = db.Column(db.String(200), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    id_doc = db.Column('cpf_nif', db.String(30), nullable=True, unique=True)
    nationality = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    emergency_contact_name = db.Column(db.String(200), nullable=True)
    emergency_contact_phone = db.Column(db.String(30), nullable=True)
    insurance_provider = db.Column(db.String(100), nullable=True)
    insurance_number = db.Column(db.String(50), nullable=True)
    photo_path = db.Column(db.String(500), nullable=True)
    anamnesis_pt = db.Column(db.Text, nullable=True)
    anamnesis_en = db.Column(db.Text, nullable=True)
    anamnesis_es = db.Column(db.Text, nullable=True)
    allergies_pt = db.Column(db.Text, nullable=True)
    allergies_en = db.Column(db.Text, nullable=True)
    allergies_es = db.Column(db.Text, nullable=True)
    medications_pt = db.Column(db.Text, nullable=True)
    medications_en = db.Column(db.Text, nullable=True)
    medications_es = db.Column(db.Text, nullable=True)
    chronic_conditions_pt = db.Column(db.Text, nullable=True)
    chronic_conditions_en = db.Column(db.Text, nullable=True)
    chronic_conditions_es = db.Column(db.Text, nullable=True)
    assigned_dentist_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id], backref='patient_profile')
    assigned_dentist = db.relationship('User', foreign_keys=[assigned_dentist_id], backref='assigned_patients')
    sessions = db.relationship('ClinicalSession', backref='patient', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic')
    care_team = db.relationship('PatientCareTeam', backref='patient', lazy='dynamic',
                                cascade='all, delete-orphan')


class PatientCareTeam(db.Model):
    """Multiple dentists can share access to a patient file (with director/superadmin approval)."""
    __tablename__ = 'patient_care_team'
    id             = db.Column(db.Integer, primary_key=True)
    patient_id     = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    dentist_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_by_id= db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status         = db.Column(db.String(20), default='pending', nullable=False)  # pending / approved / rejected
    notes          = db.Column(db.Text, nullable=True)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at    = db.Column(db.DateTime, nullable=True)

    dentist      = db.relationship('User', foreign_keys=[dentist_id],      backref='care_team_entries')
    requested_by = db.relationship('User', foreign_keys=[requested_by_id], backref='care_team_requests_made')
    approved_by  = db.relationship('User', foreign_keys=[approved_by_id],  backref='care_team_approvals')

    def status_badge(self):
        return {'pending': 'warning', 'approved': 'success', 'rejected': 'danger'}.get(self.status, 'secondary')


class Treatment(db.Model):
    __tablename__ = 'treatments'
    id = db.Column(db.Integer, primary_key=True)
    name_pt = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200), nullable=False)
    name_es = db.Column(db.String(200), nullable=False)
    description_pt = db.Column(db.Text, nullable=True)
    description_en = db.Column(db.Text, nullable=True)
    description_es = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    created_by = db.relationship('User', backref='created_treatments')

    def name_for_locale(self, locale='pt'):
        return getattr(self, f'name_{locale}', self.name_pt) or self.name_pt

    def description_for_locale(self, locale='pt'):
        return getattr(self, f'description_{locale}', self.description_pt) or self.description_pt


class Medicine(db.Model):
    __tablename__ = 'medicines'
    id = db.Column(db.Integer, primary_key=True)
    name_pt = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200), nullable=False)
    name_es = db.Column(db.String(200), nullable=False)
    active_ingredient = db.Column(db.String(200), nullable=True)
    dosage_form = db.Column(db.String(100), nullable=True)
    strength = db.Column(db.String(50), nullable=True)
    instructions_pt = db.Column(db.Text, nullable=True)
    instructions_en = db.Column(db.Text, nullable=True)
    instructions_es = db.Column(db.Text, nullable=True)
    contraindications_pt = db.Column(db.Text, nullable=True)
    contraindications_en = db.Column(db.Text, nullable=True)
    contraindications_es = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    created_by = db.relationship('User', backref='created_medicines')

    def name_for_locale(self, locale='pt'):
        return getattr(self, f'name_{locale}', self.name_pt) or self.name_pt


class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default=RoomStatus.GREEN, nullable=False)
    status_note = db.Column(db.String(200), nullable=True)
    status_updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status_updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    status_updated_by = db.relationship('User', backref='room_status_updates')
    appointments = db.relationship('Appointment', backref='room', lazy='dynamic')

    def status_badge_class(self):
        badge_map = {
            RoomStatus.GREEN: 'success',
            RoomStatus.YELLOW: 'warning',
            RoomStatus.RED: 'danger',
        }
        return badge_map.get(self.status, 'secondary')

    def status_icon(self):
        icon_map = {
            RoomStatus.GREEN: 'bi-check-circle-fill',
            RoomStatus.YELLOW: 'bi-exclamation-circle-fill',
            RoomStatus.RED: 'bi-x-circle-fill',
        }
        return icon_map.get(self.status, 'bi-circle')


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    dentist_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_emergency = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(30), default='scheduled')
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_appointments')
    clinical_sessions = db.relationship('ClinicalSession', backref='appointment', lazy='dynamic')


class ImmutableSessionError(Exception):
    """Raised when a write to a closed ClinicalSession is attempted."""


class ClinicalSession(db.Model):
    __tablename__ = 'clinical_sessions'
    id = db.Column(db.Integer, primary_key=True)
    session_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    dentist_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    session_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    chief_complaint = db.Column(db.Text, nullable=True)
    clinical_notes = db.Column(db.Text, nullable=True)
    diagnosis = db.Column(db.Text, nullable=True)
    treatment_plan = db.Column(db.Text, nullable=True)
    odontogram_data = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(30), default=SessionStatus.SCHEDULED, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys='ClinicalSession.created_by_id',
                                  backref='created_clinical_sessions')
    # Vitals snapshot at session time
    bp_systolic = db.Column(db.Integer, nullable=True)
    bp_diastolic = db.Column(db.Integer, nullable=True)
    heart_rate = db.Column(db.Integer, nullable=True)
    temperature = db.Column(db.Float, nullable=True)
    weight_kg = db.Column(db.Float, nullable=True)
    oxygen_saturation = db.Column(db.Integer, nullable=True)

    prescriptions = db.relationship('Prescription', backref='session', lazy='dynamic')
    xrays = db.relationship('XRay', backref='session', lazy='dynamic')
    evolution_photos = db.relationship('EvolutionPhoto', backref='session', lazy='dynamic')
    addenda = db.relationship('SessionAddendum', backref='session', lazy='dynamic',
                              order_by='SessionAddendum.created_at')
    session_consumables = db.relationship('SessionConsumable', backref='session',
                                          lazy='dynamic', order_by='SessionConsumable.created_at')

    # ── Model-level immutability guard ────────────────────────────────────────
    # Once status == CLOSED, no clinical or vitals field may change.
    # The only allowed post-close write is created_by_id (ignored).
    _ADMIN_ONLY_FIELDS = frozenset(['created_by_id'])

    # Fields that must never change once a session has an ID (persisted record)
    _INVARIANT_FIELDS = frozenset(['patient_id', 'dentist_id'])

    def assert_mutable(self, changed_fields=None):
        """Raise ImmutableSessionError if:
        - Any invariant field (patient_id, dentist_id) is changed (all statuses), OR
        - Any field is changed on a closed session (except _ADMIN_ONLY_FIELDS).
        """
        if changed_fields is None:
            return
        changed = frozenset(changed_fields)
        # Invariant fields: never reassignable once session is persisted
        invariant_changed = changed & self._INVARIANT_FIELDS
        if invariant_changed and self.id:  # only guard persisted sessions
            raise ImmutableSessionError(
                f"Session {self.session_code}: cannot reassign "
                f"{', '.join(sorted(invariant_changed))} after creation."
            )
        if self.status != SessionStatus.CLOSED:
            return
        blocked = changed - self._ADMIN_ONLY_FIELDS
        if blocked:
            raise ImmutableSessionError(
                f"Session {self.session_code} is closed and immutable. "
                f"Cannot modify fields: {', '.join(sorted(blocked))}"
            )

    def is_closed(self):
        return self.status == SessionStatus.CLOSED


class SessionAddendum(db.Model):
    """Signed addendum linked to a closed session — never overwrites original data."""
    __tablename__ = 'session_addenda'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('clinical_sessions.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    author = db.relationship('User', backref='authored_addenda')


class SessionTreatment(db.Model):
    __tablename__ = 'session_treatments'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('clinical_sessions.id'), nullable=False)
    treatment_id = db.Column(db.Integer, db.ForeignKey('treatments.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    notes = db.Column(db.Text, nullable=True)
    price_at_time = db.Column(db.Numeric(10, 2), nullable=True)
    urgency_surcharge_pct = db.Column(db.Numeric(5, 2), nullable=True, default=None)

    session = db.relationship('ClinicalSession', backref='session_treatments')
    treatment = db.relationship('Treatment', backref='session_uses')

    @property
    def base_price(self):
        """Original price before any urgency surcharge."""
        if self.price_at_time is None:
            return None
        if self.urgency_surcharge_pct:
            factor = 1 + float(self.urgency_surcharge_pct) / 100
            return float(self.price_at_time) / factor
        return float(self.price_at_time)

    @property
    def surcharge_amount(self):
        """The monetary amount added due to urgency."""
        if self.urgency_surcharge_pct and self.price_at_time:
            return float(self.price_at_time) - (float(self.price_at_time) / (1 + float(self.urgency_surcharge_pct) / 100))
        return 0.0


class Prescription(db.Model):
    __tablename__ = 'prescriptions'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('clinical_sessions.id'), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'), nullable=False)
    dosage = db.Column(db.String(100), nullable=True)
    frequency = db.Column(db.String(100), nullable=True)
    duration = db.Column(db.String(100), nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    medicine = db.relationship('Medicine', backref='prescriptions')


class XRay(db.Model):
    __tablename__ = 'xrays'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('clinical_sessions.id'), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(10), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    uploaded_by = db.relationship('User', backref='uploaded_xrays')


class EvolutionPhoto(db.Model):
    __tablename__ = 'evolution_photos'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('clinical_sessions.id'), nullable=True)
    photo_type = db.Column(db.String(20), nullable=False, default='before')
    file_path = db.Column(db.String(500), nullable=False)
    caption = db.Column(db.String(200), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    patient = db.relationship('Patient', backref='evolution_photos')
    uploaded_by = db.relationship('User', backref='uploaded_evolution_photos')


class AppSetting(db.Model):
    """Key-value store for customisable application settings."""
    __tablename__ = 'app_settings'

    key   = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=True)

    _DEFAULTS = {
        'app_name':       'DentalCare Pro',
        'app_logo':       '',
        # Dark mode — structure
        'bg_dark':        '#111111',
        'sidebar_dark':   '#181818',
        'card_dark':      '#1e1e1e',
        'border_dark':    '#2d2d2d',
        'text_dark':      '#d4d4d4',
        # Dark mode — accents
        'primary_dark':   '#14b8a6',
        'success_dark':   '#22c55e',
        'danger_dark':    '#f87171',
        'warning_dark':   '#fbbf24',
        # Light mode — structure
        'bg_light':       '#f0f4f8',
        'card_light':     '#ffffff',
        'border_light':   '#d1dce8',
        'text_light':     '#334155',
        # Light mode — accents
        'primary_light':  '#1976d2',
        'success_light':  '#00875a',
        'danger_light':   '#d32f2f',
        'warning_light':  '#e65100',
        'xray_max_mb':        '10',
        'stock_invoice_max_mb': '5',
        'urgency_surcharge':  '30',
    }

    @classmethod
    def get(cls, key, default=None):
        s = cls.query.filter_by(key=key).first()
        if s is not None:
            return s.value
        return cls._DEFAULTS.get(key, default)

    @classmethod
    def set(cls, key, value):
        s = cls.query.filter_by(key=key).first()
        if s is None:
            s = cls(key=key, value=value)
            db.session.add(s)
        else:
            s.value = value
        db.session.commit()

    @classmethod
    def all_as_dict(cls):
        stored = {s.key: s.value for s in cls.query.all()}
        result = dict(cls._DEFAULTS)
        result.update(stored)
        return result


class StockCategory:
    EPI          = 'epi'
    ANESTESIA    = 'anestesia'
    RESTAURACAO  = 'restauracao'
    INSTRUMENTAL = 'instrumental'
    HIGIENE      = 'higiene'
    MEDICAMENTOS = 'medicamentos'
    OUTROS       = 'outros'

    LABELS = {
        'epi':          'EPI',
        'anestesia':    'Anestesia',
        'restauracao':  'Restauração',
        'instrumental': 'Instrumental',
        'higiene':      'Higiene / Esterilização',
        'medicamentos': 'Medicamentos',
        'outros':       'Outros',
    }
    ICONS = {
        'epi':          'bi-shield-fill-plus',
        'anestesia':    'bi-syringe-fill',
        'restauracao':  'bi-gem',
        'instrumental': 'bi-tools',
        'higiene':      'bi-droplet-fill',
        'medicamentos': 'bi-capsule-pill',
        'outros':       'bi-box-seam-fill',
    }


class StockProduct(db.Model):
    __tablename__ = 'stock_products'

    id           = db.Column(db.Integer, primary_key=True)
    name_pt      = db.Column(db.String(200), nullable=False)
    name_en      = db.Column(db.String(200), nullable=True)
    name_es      = db.Column(db.String(200), nullable=True)
    category     = db.Column(db.String(50), nullable=False, default='outros')
    unit         = db.Column(db.String(30), nullable=False, default='unidade')
    qty_current  = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    qty_minimum  = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    unit_cost    = db.Column(db.Numeric(10, 2), nullable=True)
    supplier     = db.Column(db.String(200), nullable=True)
    notes        = db.Column(db.Text, nullable=True)
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    created_by  = db.relationship('User', backref='stock_products')
    movements   = db.relationship('StockMovement', backref='product', lazy='dynamic',
                                  order_by='StockMovement.created_at.desc()')

    @property
    def is_low_stock(self):
        return float(self.qty_current) < float(self.qty_minimum)

    @property
    def stock_value(self):
        if self.unit_cost and self.qty_current:
            return round(float(self.qty_current) * float(self.unit_cost), 2)
        return 0.0

    @property
    def category_label(self):
        return StockCategory.LABELS.get(self.category, self.category)

    @property
    def category_icon(self):
        return StockCategory.ICONS.get(self.category, 'bi-box-seam-fill')


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'

    id                = db.Column(db.Integer, primary_key=True)
    product_id        = db.Column(db.Integer, db.ForeignKey('stock_products.id'), nullable=False)
    movement_type     = db.Column(db.String(10), nullable=False)   # 'in' | 'out'
    reason            = db.Column(db.String(50), nullable=False)
    quantity          = db.Column(db.Numeric(10, 2), nullable=False)
    qty_after         = db.Column(db.Numeric(10, 2), nullable=True)
    unit_cost         = db.Column(db.Numeric(10, 2), nullable=True)
    session_id        = db.Column(db.Integer, db.ForeignKey('clinical_sessions.id'), nullable=True)
    notes             = db.Column(db.Text, nullable=True)
    invoice_file_path = db.Column(db.String(500), nullable=True)
    invoice_file_name = db.Column(db.String(255), nullable=True)
    created_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    created_by_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    created_by = db.relationship('User', backref='stock_movements')
    session    = db.relationship('ClinicalSession', backref='stock_movements')

    IN_REASONS  = {'compra': 'Compra', 'devolucao': 'Devolução', 'doacao': 'Doação', 'ajuste': 'Ajuste +'}
    OUT_REASONS = {'uso': 'Uso em Sessão', 'validade': 'Validade/Descarte', 'perda': 'Perda', 'ajuste': 'Ajuste −'}

    @property
    def reason_label(self):
        if self.movement_type == 'in':
            return self.IN_REASONS.get(self.reason, self.reason)
        return self.OUT_REASONS.get(self.reason, self.reason)


class SessionConsumable(db.Model):
    __tablename__ = 'session_consumables'

    id                 = db.Column(db.Integer, primary_key=True)
    session_id         = db.Column(db.Integer, db.ForeignKey('clinical_sessions.id'), nullable=False)
    product_id         = db.Column(db.Integer, db.ForeignKey('stock_products.id'), nullable=False)
    quantity           = db.Column(db.Numeric(10, 2), nullable=False)
    unit_cost_snapshot = db.Column(db.Numeric(10, 2), nullable=True)
    notes              = db.Column(db.String(200), nullable=True)
    created_at         = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    stock_movement_id  = db.Column(db.Integer, db.ForeignKey('stock_movements.id'), nullable=True)

    product        = db.relationship('StockProduct', backref='session_usages')
    created_by     = db.relationship('User', backref='session_consumables')
    stock_movement = db.relationship('StockMovement', backref='session_consumable',
                                     foreign_keys=[stock_movement_id])

    @property
    def total_cost(self):
        if self.unit_cost_snapshot and self.quantity:
            return round(float(self.unit_cost_snapshot) * float(self.quantity), 2)
        return 0.0


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(80), nullable=True)
    action = db.Column(db.String(20), nullable=False)
    table_name = db.Column(db.String(100), nullable=False)
    record_id = db.Column(db.Integer, nullable=True)
    old_value = db.Column(db.JSON, nullable=True)
    new_value = db.Column(db.JSON, nullable=True)
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user = db.relationship('User', backref='audit_entries')
