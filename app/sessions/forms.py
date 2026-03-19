from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, TextAreaField, SelectField,
                     SelectMultipleField, HiddenField, SubmitField, IntegerField, DecimalField)
from wtforms.validators import Optional, Length, NumberRange


class SessionForm(FlaskForm):
    chief_complaint = TextAreaField('Queixa Principal', validators=[Optional(), Length(max=500)])
    clinical_notes = TextAreaField('Notas Clínicas', validators=[Optional()])
    diagnosis = TextAreaField('Diagnóstico', validators=[Optional()])
    treatment_plan = TextAreaField('Plano de Tratamento', validators=[Optional()])
    odontogram_data = HiddenField('Odontograma JSON', validators=[Optional()])
    treatments = SelectMultipleField('Tratamentos Realizados', coerce=int, validators=[Optional()])
    # Vitals
    bp_systolic     = IntegerField('Sistólica (mmHg)',   validators=[Optional(), NumberRange(40, 300)])
    bp_diastolic    = IntegerField('Diastólica (mmHg)',  validators=[Optional(), NumberRange(20, 200)])
    heart_rate      = IntegerField('Freq. Cardíaca (bpm)', validators=[Optional(), NumberRange(20, 300)])
    temperature     = DecimalField('Temperatura (°C)',   validators=[Optional(), NumberRange(30.0, 45.0)], places=1)
    weight_kg       = DecimalField('Peso (kg)',          validators=[Optional(), NumberRange(1.0, 500.0)], places=1)
    oxygen_saturation = IntegerField('SpO₂ (%)',         validators=[Optional(), NumberRange(50, 100)])
    status = SelectField('Estado', choices=[
        ('in_progress', 'Em Progresso'),
        ('closed', 'Fechar Sessão'),
        ('cancelled', 'Cancelar'),
    ])
    submit = SubmitField('Guardar')


class PrescriptionForm(FlaskForm):
    medicine_id = SelectField('Medicamento', coerce=int, validators=[Optional()])
    dosage = StringField('Dosagem', validators=[Optional(), Length(max=100)])
    frequency = StringField('Frequência', validators=[Optional(), Length(max=100)])
    duration = StringField('Duração', validators=[Optional(), Length(max=100)])
    instructions = TextAreaField('Instruções', validators=[Optional()])
    submit = SubmitField('Adicionar Prescrição')


class XRayUploadForm(FlaskForm):
    file = FileField('Ficheiro', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Apenas JPG, PNG ou PDF.')
    ])
    notes = TextAreaField('Notas', validators=[Optional()])
    submit = SubmitField('Carregar')


class EvolutionPhotoForm(FlaskForm):
    photo_type = SelectField('Tipo', choices=[('before', 'Antes'), ('after', 'Depois')])
    file = FileField('Fotografia', validators=[
        FileAllowed(['jpg', 'jpeg', 'png'], 'Apenas JPG ou PNG.')
    ])
    caption = StringField('Legenda', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Carregar')


class AddendumForm(FlaskForm):
    addendum_text = TextAreaField('Adenda (Diretor Clínico)', validators=[Optional()])
    submit = SubmitField('Guardar Adenda')
