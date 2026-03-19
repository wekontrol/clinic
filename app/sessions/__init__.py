from flask import Blueprint

sessions_bp = Blueprint('sessions', __name__, url_prefix='/sessions')

from . import routes      # noqa: F401, E402
from . import pdf_routes  # noqa: F401, E402
