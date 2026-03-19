import os
import uuid
from datetime import datetime, timezone
from flask import (render_template, redirect, url_for, flash, request, abort,
                   current_app, send_from_directory)
from flask_login import login_required, current_user
from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from . import stock_bp
from .forms import StockProductForm, StockMovementForm, IN_REASON_CHOICES, OUT_REASON_CHOICES
from ..models import StockProduct, StockMovement, StockCategory, Role, AppSetting
from ..extensions import db
from ..audit import log_action


ALLOWED_INVOICE = {'pdf', 'jpg', 'jpeg', 'png'}


def _save_invoice(file):
    """Save an uploaded invoice file; return relative path or None."""
    if not file or not file.filename:
        return None, None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_INVOICE:
        return None, None
    max_mb  = int(AppSetting.get('stock_invoice_max_mb', 5))
    max_bytes = max_mb * 1024 * 1024
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > max_bytes:
        return None, f'too_large:{max_mb}'
    dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'stock_invoices')
    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    file.save(os.path.join(dest_dir, filename))
    return os.path.join('stock_invoices', filename), file.filename


def _require_stock_access(write=False):
    """Raise 403 if user can't access stock. write=True requires manager role."""
    if current_user.role == Role.PATIENT:
        abort(403)
    if write and current_user.role == Role.DENTIST:
        abort(403)


# ─── INDEX ────────────────────────────────────────────────────────────────────

@stock_bp.route('/')
@login_required
def index():
    _require_stock_access()
    cat_filter = request.args.get('cat', '')

    q = StockProduct.query.filter_by(is_active=True)
    if cat_filter:
        q = q.filter_by(category=cat_filter)
    products = q.order_by(StockProduct.category, StockProduct.name_pt).all()

    # KPIs
    all_active = StockProduct.query.filter_by(is_active=True).all()
    total_products   = len(all_active)
    low_stock_items  = [p for p in all_active if p.is_low_stock and float(p.qty_minimum) > 0]
    out_of_stock     = [p for p in all_active if float(p.qty_current) == 0]
    total_value      = sum(p.stock_value for p in all_active)

    # Recent movements (last 10)
    recent_movements = StockMovement.query.order_by(
        StockMovement.created_at.desc()).limit(10).all()

    categories = StockCategory.LABELS

    return render_template('stock/index.html',
        products=products,
        total_products=total_products,
        low_stock_items=low_stock_items,
        out_of_stock=out_of_stock,
        total_value=total_value,
        recent_movements=recent_movements,
        categories=categories,
        cat_filter=cat_filter,
        StockCategory=StockCategory,
    )


# ─── NEW PRODUCT ──────────────────────────────────────────────────────────────

@stock_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_product():
    _require_stock_access(write=True)
    form = StockProductForm()
    if form.validate_on_submit():
        p = StockProduct(
            name_pt      = form.name_pt.data.strip(),
            name_en      = form.name_en.data.strip() or None,
            name_es      = form.name_es.data.strip() or None,
            category     = form.category.data,
            unit         = form.unit.data,
            qty_current  = form.qty_current.data or 0,
            qty_minimum  = form.qty_minimum.data or 0,
            unit_cost    = form.unit_cost.data,
            supplier     = form.supplier.data.strip() or None,
            notes        = form.notes.data.strip() or None,
            is_active    = form.is_active.data,
            created_by_id= current_user.id,
        )
        db.session.add(p)
        db.session.flush()

        # Handle invoice attachment
        inv_path, inv_name_or_err = _save_invoice(request.files.get('invoice_file'))
        if inv_name_or_err and inv_name_or_err.startswith('too_large:'):
            max_mb = inv_name_or_err.split(':')[1]
            flash(_(f'Ficheiro de fatura excede o limite de {max_mb} MB.'), 'danger')
            return render_template('stock/product_form.html', form=form, product=None,
                                   stock_invoice_max_mb=int(AppSetting.get('stock_invoice_max_mb', 5)))

        # Initial stock movement if qty > 0
        if form.qty_current.data and float(form.qty_current.data) > 0:
            mv = StockMovement(
                product_id        = p.id,
                movement_type     = 'in',
                reason            = 'compra' if inv_path else 'ajuste',
                quantity          = form.qty_current.data,
                qty_after         = form.qty_current.data,
                unit_cost         = form.unit_cost.data,
                notes             = _('Stock inicial'),
                invoice_file_path = inv_path,
                invoice_file_name = inv_name_or_err if inv_path else None,
                created_by_id     = current_user.id,
            )
            db.session.add(mv)

        db.session.commit()
        log_action('stock_products', 'CREATE', record_id=p.id,
                   new_value={'name': p.name_pt},
                   description=f'Stock product created: {p.name_pt}')
        flash(_(f'Produto «{p.name_pt}» criado.'), 'success')
        return redirect(url_for('stock.detail', product_id=p.id))

    stock_invoice_max_mb = int(AppSetting.get('stock_invoice_max_mb', 5))
    return render_template('stock/product_form.html', form=form, product=None,
                           stock_invoice_max_mb=stock_invoice_max_mb)


# ─── DETAIL ───────────────────────────────────────────────────────────────────

@stock_bp.route('/<int:product_id>')
@login_required
def detail(product_id):
    _require_stock_access()
    product = StockProduct.query.get_or_404(product_id)
    movements = product.movements.limit(50).all()
    can_manage = current_user.role in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR, Role.RECEPTION]
    return render_template('stock/product_detail.html',
        product=product, movements=movements, can_manage=can_manage)


# ─── EDIT ─────────────────────────────────────────────────────────────────────

@stock_bp.route('/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    _require_stock_access(write=True)
    product = StockProduct.query.get_or_404(product_id)
    form = StockProductForm(obj=product)
    if form.validate_on_submit():
        old = {'name': product.name_pt}
        product.name_pt    = form.name_pt.data.strip()
        product.name_en    = form.name_en.data.strip() or None
        product.name_es    = form.name_es.data.strip() or None
        product.category   = form.category.data
        product.unit       = form.unit.data
        product.qty_minimum= form.qty_minimum.data or 0
        product.unit_cost  = form.unit_cost.data
        product.supplier   = form.supplier.data.strip() or None
        product.notes      = form.notes.data.strip() or None
        product.is_active  = form.is_active.data
        db.session.commit()
        log_action('stock_products', 'UPDATE', record_id=product.id,
                   old_value=old, new_value={'name': product.name_pt},
                   description=f'Stock product updated: {product.name_pt}')
        flash(_('Produto actualizado.'), 'success')
        return redirect(url_for('stock.detail', product_id=product.id))

    return render_template('stock/product_form.html', form=form, product=product)


# ─── MOVEMENT ─────────────────────────────────────────────────────────────────

@stock_bp.route('/<int:product_id>/movement', methods=['GET', 'POST'])
@login_required
def add_movement(product_id):
    _require_stock_access(write=True)
    # Receptionists can only add IN movements
    if current_user.role == Role.RECEPTION:
        _type = 'in'
    else:
        _type = request.args.get('type', 'in')

    product = StockProduct.query.get_or_404(product_id)
    form = StockMovementForm()

    # Populate reason choices based on type
    if _type == 'in':
        form.reason.choices = IN_REASON_CHOICES
        form.movement_type.data = 'in'
    else:
        form.reason.choices = OUT_REASON_CHOICES
        form.movement_type.data = 'out'

    if form.validate_on_submit():
        mv_type = form.movement_type.data
        qty     = float(form.quantity.data)

        # Handle invoice upload (only for IN movements)
        inv_path, inv_name_or_err = None, None
        if mv_type == 'in':
            inv_path, inv_name_or_err = _save_invoice(request.files.get('invoice_file'))
            if inv_name_or_err and inv_name_or_err.startswith('too_large:'):
                max_mb = inv_name_or_err.split(':')[1]
                flash(_(f'Ficheiro de fatura excede o limite de {max_mb} MB.'), 'danger')
                return render_template('stock/movement_form.html',
                    form=form, product=product, mv_type=_type,
                    in_reasons=IN_REASON_CHOICES, out_reasons=OUT_REASON_CHOICES,
                    stock_invoice_max_mb=int(AppSetting.get('stock_invoice_max_mb', 5)))

        if mv_type == 'out' and qty > float(product.qty_current):
            flash(_('Quantidade insuficiente em stock.'), 'danger')
        else:
            if mv_type == 'in':
                product.qty_current = float(product.qty_current) + qty
            else:
                product.qty_current = float(product.qty_current) - qty

            mv = StockMovement(
                product_id        = product.id,
                movement_type     = mv_type,
                reason            = form.reason.data,
                quantity          = qty,
                qty_after         = product.qty_current,
                unit_cost         = form.unit_cost.data,
                notes             = form.notes.data.strip() or None,
                invoice_file_path = inv_path,
                invoice_file_name = inv_name_or_err if inv_path else None,
                created_by_id     = current_user.id,
            )
            db.session.add(mv)
            db.session.commit()
            log_action('stock_movements', 'CREATE', record_id=mv.id,
                       new_value={'product': product.name_pt, 'type': mv_type, 'qty': qty},
                       description=f'Stock movement: {mv_type} {qty} {product.unit} of {product.name_pt}')
            direction = _('Entrada') if mv_type == 'in' else _('Saída')
            flash(_(f'{direction} de {qty} {product.unit} registada.'), 'success')
            return redirect(url_for('stock.detail', product_id=product.id))

    stock_invoice_max_mb = int(AppSetting.get('stock_invoice_max_mb', 5))
    return render_template('stock/movement_form.html',
        form=form, product=product, mv_type=_type,
        in_reasons=IN_REASON_CHOICES, out_reasons=OUT_REASON_CHOICES,
        stock_invoice_max_mb=stock_invoice_max_mb)


# ─── SERVE INVOICE ────────────────────────────────────────────────────────────

@stock_bp.route('/invoice/<int:mv_id>')
@login_required
def serve_invoice(mv_id):
    _require_stock_access()
    mv = StockMovement.query.get_or_404(mv_id)
    if not mv.invoice_file_path:
        abort(404)
    full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], mv.invoice_file_path)
    directory = os.path.dirname(full_path)
    filename  = os.path.basename(full_path)
    return send_from_directory(directory, filename,
                               download_name=mv.invoice_file_name or filename)


# ─── DELETE (SOFT) ────────────────────────────────────────────────────────────

@stock_bp.route('/<int:product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    if current_user.role not in [Role.SUPERADMIN, Role.CLINICAL_DIRECTOR]:
        abort(403)
    product = StockProduct.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()
    log_action('stock_products', 'DELETE', record_id=product.id,
               description=f'Stock product deactivated: {product.name_pt}')
    flash(_('Produto desactivado.'), 'warning')
    return redirect(url_for('stock.index'))
