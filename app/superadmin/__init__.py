from flask import Blueprint

superadmin_bp = Blueprint('superadmin', __name__)

from . import routes  # noqa: F401, E402
