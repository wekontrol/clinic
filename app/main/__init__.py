from flask import Blueprint

main_bp = Blueprint('main', __name__)

from . import routes      # noqa: F401, E402
from . import kpi_routes  # noqa: F401, E402
