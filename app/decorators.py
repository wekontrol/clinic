from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from .models import Role


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            allowed = [r.value if isinstance(r, Role) else r for r in roles]
            if current_user.role not in allowed:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def superadmin_required(f):
    return role_required(Role.SUPERADMIN)(f)


def director_or_superadmin_required(f):
    return role_required(Role.SUPERADMIN, Role.CLINICAL_DIRECTOR)(f)


def clinical_staff_required(f):
    return role_required(Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST)(f)


def not_patient_required(f):
    return role_required(Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.DENTIST, Role.RECEPTION)(f)
