from flask import Blueprint

stock_bp = Blueprint('stock', __name__, url_prefix='/stock')

from . import routes  # noqa: F401, E402
