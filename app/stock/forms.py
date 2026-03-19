from flask_wtf import FlaskForm
from wtforms import (StringField, SelectField, DecimalField, IntegerField,
                     TextAreaField, BooleanField, FloatField)
from wtforms.validators import DataRequired, Optional, Length, NumberRange
from flask_babel import lazy_gettext as _l

CATEGORY_CHOICES = [
    ('epi',          'EPI (Luvas, Máscaras…)'),
    ('anestesia',    'Anestesia'),
    ('restauracao',  'Material de Restauração'),
    ('instrumental', 'Instrumental'),
    ('higiene',      'Higiene / Esterilização'),
    ('medicamentos', 'Medicamentos'),
    ('outros',       'Outros'),
]

UNIT_CHOICES = [
    ('unidade',  'Unidade'),
    ('caixa',    'Caixa'),
    ('pacote',   'Pacote'),
    ('rolo',     'Rolo'),
    ('par',      'Par'),
    ('ml',       'ml'),
    ('L',        'L (litro)'),
    ('mg',       'mg'),
    ('g',        'g (grama)'),
    ('ampola',   'Ampola'),
    ('seringa',  'Seringa'),
    ('resma',    'Resma'),
]

IN_REASON_CHOICES = [
    ('compra',   'Compra'),
    ('devolucao','Devolução'),
    ('doacao',   'Doação'),
    ('ajuste',   'Ajuste de Inventário (+)'),
]

OUT_REASON_CHOICES = [
    ('uso',      'Uso em Sessão'),
    ('validade', 'Validade / Descarte'),
    ('perda',    'Perda'),
    ('ajuste',   'Ajuste de Inventário (−)'),
]


class StockProductForm(FlaskForm):
    name_pt   = StringField(_l('Nome (PT)'), validators=[DataRequired(), Length(1, 200)])
    name_en   = StringField(_l('Nome (EN)'), validators=[Optional(), Length(0, 200)])
    name_es   = StringField(_l('Nome (ES)'), validators=[Optional(), Length(0, 200)])
    category  = SelectField(_l('Categoria'), choices=CATEGORY_CHOICES, validators=[DataRequired()])
    unit      = SelectField(_l('Unidade'), choices=UNIT_CHOICES, validators=[DataRequired()])
    qty_current = DecimalField(_l('Qtd. Actual'), validators=[Optional(), NumberRange(min=0)], places=2, default=0)
    qty_minimum = DecimalField(_l('Qtd. Mínima (alerta)'), validators=[Optional(), NumberRange(min=0)], places=2, default=0)
    unit_cost   = DecimalField(_l('Custo Unitário (Kz)'), validators=[Optional(), NumberRange(min=0)], places=2)
    supplier    = StringField(_l('Fornecedor'), validators=[Optional(), Length(0, 200)])
    notes       = TextAreaField(_l('Notas'), validators=[Optional(), Length(0, 1000)])
    is_active   = BooleanField(_l('Activo'), default=True)


class StockMovementForm(FlaskForm):
    movement_type = SelectField(_l('Tipo'), choices=[('in', 'Entrada'), ('out', 'Saída')],
                                validators=[DataRequired()])
    reason        = SelectField(_l('Motivo'), choices=[], validators=[DataRequired()])
    quantity      = DecimalField(_l('Quantidade'), validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    unit_cost     = DecimalField(_l('Custo Unitário (Kz)'), validators=[Optional(), NumberRange(min=0)], places=2)
    notes         = TextAreaField(_l('Notas'), validators=[Optional(), Length(0, 500)])
