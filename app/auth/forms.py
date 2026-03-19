from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from flask_babel import lazy_gettext as _l


class LoginForm(FlaskForm):
    username = StringField(_l('Utilizador'), validators=[DataRequired(), Length(1, 80)])
    password = PasswordField(_l('Senha'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Lembrar-me'))
    submit = SubmitField(_l('Entrar'))


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(_l('Senha Atual'), validators=[DataRequired()])
    new_password = PasswordField(_l('Nova Senha'), validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(_l('Confirmar Nova Senha'),
                                     validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField(_l('Alterar Senha'))

    def validate_new_password(self, field):
        if len(field.data) < 6:
            raise ValidationError(_l('A senha deve ter pelo menos 6 caracteres.'))
