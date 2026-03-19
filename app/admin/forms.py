from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, IntegerField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Optional, Length
from flask_babel import lazy_gettext as _l


class TreatmentForm(FlaskForm):
    name_pt = StringField(_l('Nome (PT)'), validators=[DataRequired(), Length(1, 200)])
    name_en = StringField(_l('Name (EN)'), validators=[DataRequired(), Length(1, 200)])
    name_es = StringField(_l('Nombre (ES)'), validators=[DataRequired(), Length(1, 200)])
    description_pt = TextAreaField(_l('Descrição (PT)'), validators=[Optional()])
    description_en = TextAreaField(_l('Description (EN)'), validators=[Optional()])
    description_es = TextAreaField(_l('Descripción (ES)'), validators=[Optional()])
    category = StringField(_l('Categoria'), validators=[Optional(), Length(0, 100)])
    price = DecimalField(_l('Preço (€)'), validators=[Optional()], places=2)
    duration_minutes = IntegerField(_l('Duração (min)'), validators=[Optional()])
    is_active = BooleanField(_l('Ativo'), default=True)
    submit = SubmitField(_l('Guardar'))


class MedicineForm(FlaskForm):
    name_pt = StringField(_l('Nome (PT)'), validators=[DataRequired(), Length(1, 200)])
    name_en = StringField(_l('Name (EN)'), validators=[DataRequired(), Length(1, 200)])
    name_es = StringField(_l('Nombre (ES)'), validators=[DataRequired(), Length(1, 200)])
    active_ingredient = StringField(_l('Princípio Ativo'), validators=[Optional(), Length(0, 200)])
    dosage_form = StringField(_l('Forma Farmacêutica'), validators=[Optional(), Length(0, 100)])
    strength = StringField(_l('Dosagem/Concentração'), validators=[Optional(), Length(0, 50)])
    instructions_pt = TextAreaField(_l('Instruções (PT)'), validators=[Optional()])
    instructions_en = TextAreaField(_l('Instructions (EN)'), validators=[Optional()])
    instructions_es = TextAreaField(_l('Instrucciones (ES)'), validators=[Optional()])
    contraindications_pt = TextAreaField(_l('Contraindicações (PT)'), validators=[Optional()])
    contraindications_en = TextAreaField(_l('Contraindications (EN)'), validators=[Optional()])
    contraindications_es = TextAreaField(_l('Contraindicaciones (ES)'), validators=[Optional()])
    is_active = BooleanField(_l('Ativo'), default=True)
    submit = SubmitField(_l('Guardar'))


class UserForm(FlaskForm):
    username = StringField(_l('Utilizador'), validators=[DataRequired(), Length(1, 80)])
    email = StringField(_l('Email'), validators=[DataRequired(), Length(1, 120)])
    full_name = StringField(_l('Nome Completo'), validators=[DataRequired(), Length(1, 200)])
    role = SelectField(_l('Perfil'), choices=[
        ('superadmin', 'Superadmin'),
        ('clinical_director', 'Diretor Clínico'),
        ('dentist', 'Dentista'),
        ('patient', 'Paciente'),
        ('reception', 'Recepção'),
    ], validators=[DataRequired()])
    phone = StringField(_l('Telefone'), validators=[Optional()])
    specialty = StringField(_l('Especialidade'), validators=[Optional()])
    license_number = StringField(_l('Nº Ordem dos Médicos'), validators=[Optional(), Length(0, 50)])
    is_active = BooleanField(_l('Ativo'), default=True)
    submit = SubmitField(_l('Guardar'))
