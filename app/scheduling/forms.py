from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, DateTimeLocalField, SelectField,
                     BooleanField, SubmitField, HiddenField)
from wtforms.validators import DataRequired, Optional, Length
from flask_babel import lazy_gettext as _l


class AppointmentForm(FlaskForm):
    patient_id = SelectField(_l('Paciente'), coerce=int, validators=[DataRequired()])
    dentist_id = SelectField(_l('Dentista'), coerce=int, validators=[DataRequired()])
    room_id = SelectField(_l('Sala'), coerce=int, validators=[Optional()])
    start_time = DateTimeLocalField(_l('Início'), format='%Y-%m-%dT%H:%M',
                                    validators=[DataRequired()])
    end_time = DateTimeLocalField(_l('Fim'), format='%Y-%m-%dT%H:%M',
                                  validators=[Optional()])
    notes = TextAreaField(_l('Notas'), validators=[Optional(), Length(0, 2000)])
    is_emergency = BooleanField(_l('Urgência'), default=False)
    submit = SubmitField(_l('Guardar'))


class EmergencyForm(FlaskForm):
    patient_name = StringField(_l('Nome do Paciente (ou ID)'), validators=[Optional(), Length(0, 200)])
    patient_id = SelectField(_l('Paciente Cadastrado'), coerce=int, validators=[Optional()])
    dentist_id = SelectField(_l('Dentista'), coerce=int, validators=[DataRequired()])
    room_id = SelectField(_l('Sala'), coerce=int, validators=[DataRequired()])
    notes = TextAreaField(_l('Motivo da Urgência'), validators=[Optional(), Length(0, 500)])
    submit = SubmitField(_l('Registar Urgência'))


class RoomStatusForm(FlaskForm):
    room_id = HiddenField()
    status = SelectField(_l('Estado'), choices=[
        ('green', 'Verde — Disponível'),
        ('yellow', 'Amarelo — Em Uso'),
        ('red', 'Vermelho — Emergência'),
    ], validators=[DataRequired()])
    status_note = StringField(_l('Nota'), validators=[Optional(), Length(0, 200)])
    submit = SubmitField(_l('Atualizar'))
