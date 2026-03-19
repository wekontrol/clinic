from flask import Blueprint

scheduling_bp = Blueprint('scheduling', __name__, url_prefix='/scheduling')

from . import routes
