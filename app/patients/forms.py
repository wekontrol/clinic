import os
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, TextAreaField, DateField, SelectField,
                     BooleanField, SubmitField)
from wtforms.validators import DataRequired, Optional, Length, Email
from flask_babel import lazy_gettext as _l


class PatientForm(FlaskForm):
    full_name = StringField(_l('Nome Completo'), validators=[DataRequired(), Length(1, 200)])
    date_of_birth = DateField(_l('Data de Nascimento'), validators=[Optional()])
    gender = SelectField(_l('Género'), choices=[
        ('', '---'),
        ('male', 'Masculino'),
        ('female', 'Feminino'),
        ('other', 'Outro'),
    ], validators=[Optional()])
    id_doc = StringField(_l('Documento de Identificação (BI / Passaporte)'), validators=[Optional(), Length(0, 30)])
    nationality = StringField(_l('Nacionalidade'), validators=[Optional(), Length(0, 100)])
    address = TextAreaField(_l('Morada'), validators=[Optional()])
    city = StringField(_l('Município / Cidade'), validators=[Optional(), Length(0, 100)])
    phone = StringField(_l('Telefone'), validators=[Optional(), Length(0, 30)])
    email = StringField(_l('Email'), validators=[Optional(), Email(), Length(0, 120)])
    emergency_contact_name = StringField(_l('Contacto de Emergência'), validators=[Optional(), Length(0, 200)])
    emergency_contact_phone = StringField(_l('Telefone de Emergência'), validators=[Optional(), Length(0, 30)])
    insurance_provider = StringField(_l('Seguradora'), validators=[Optional(), Length(0, 100)])
    insurance_number = StringField(_l('Nº de Apólice'), validators=[Optional(), Length(0, 50)])
    assigned_dentist_id = SelectField(_l('Dentista Responsável'), coerce=int,
                                      validators=[Optional()])
    photo = FileField(_l('Foto de Perfil'), validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], _l('Apenas imagens JPG/PNG são aceites.'))
    ])
    anamnesis_pt = TextAreaField(_l('Anamnese (PT)'), validators=[Optional()])
    anamnesis_en = TextAreaField(_l('Anamnesis (EN)'), validators=[Optional()])
    anamnesis_es = TextAreaField(_l('Anamnesis (ES)'), validators=[Optional()])
    allergies_pt = TextAreaField(_l('Alergias (PT)'), validators=[Optional()])
    allergies_en = TextAreaField(_l('Allergies (EN)'), validators=[Optional()])
    allergies_es = TextAreaField(_l('Alergias (ES)'), validators=[Optional()])
    medications_pt = TextAreaField(_l('Medicação Atual (PT)'), validators=[Optional()])
    medications_en = TextAreaField(_l('Current Medications (EN)'), validators=[Optional()])
    medications_es = TextAreaField(_l('Medicación Actual (ES)'), validators=[Optional()])
    chronic_conditions_pt = TextAreaField(_l('Doenças Crónicas (PT)'), validators=[Optional()])
    chronic_conditions_en = TextAreaField(_l('Chronic Conditions (EN)'), validators=[Optional()])
    chronic_conditions_es = TextAreaField(_l('Enfermedades Crónicas (ES)'), validators=[Optional()])
    is_active = BooleanField(_l('Ativo'), default=True)
    submit = SubmitField(_l('Guardar Paciente'))
