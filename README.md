# 🦷 DentClinic — Sistema de Gestão de Clínica Dentária

Sistema profissional de gestão clínica dentária desenvolvido em Python/Flask, com suporte trilingue (PT/EN/ES), RBAC com 5 perfis, modo escuro/claro e instalação simples em Ubuntu Server.

---

## ⚡ Instalação Rápida (Ubuntu Server 22.04 / 24.04)

```bash
git clone https://github.com/SEU_UTILIZADOR/clinic.git
cd clinic
sudo bash install.sh
```

Acesso em `http://IP_DO_SERVIDOR` — login: **admin** / senha: **admin**

---

## ✨ Funcionalidades

| Módulo | Descrição |
|---|---|
| **Pacientes** | Ficha completa, odontograma SVG, galeria de evolução, doc. identificação |
| **Sessões Clínicas** | Rastreabilidade clínica, anamnese, prescrições, consumíveis de stock |
| **Agenda** | FullCalendar.js, 2 salas, urgências, vista mobile responsiva |
| **Equipa Clínica** | Multi-dentista por paciente com fluxo de aprovação |
| **Stock** | Gestão de produtos com movimentos, faturas em PDF/imagem |
| **Medicamentos** | Catálogo com princípios ativos e formas farmacêuticas |
| **Utilizadores** | RBAC: Superadmin, Diretor Clínico, Dentista, Receção, Paciente |
| **Relatórios PDF** | Plano de tratamento, consentimento informado, fichas clínicas |
| **Auditoria** | Registo completo de todas as ações com filtros avançados |
| **Painel Superadmin** | Monitor de sistema (psutil), backup/restauro, personalização |
| **Multilingue** | Português (padrão), Inglês, Espanhol |

---

## 🛠 Requisitos

- Ubuntu Server 22.04 LTS ou 24.04 LTS
- Python 3.10+
- Nginx (instalado automaticamente)
- 512 MB RAM mínimo

---

## 🔧 Instalação Manual (passo a passo)

```bash
# 1. Clonar o repositório
git clone https://github.com/SEU_UTILIZADOR/clinic.git /opt/clinic
cd /opt/clinic

# 2. Criar ambiente virtual e instalar dependências
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp instance/.env.example instance/.env
# Editar instance/.env com as suas configurações

# 4. Iniciar a aplicação
python run.py
```

---

## ⚙️ Configuração (`instance/.env`)

```env
SECRET_KEY=chave-secreta-forte-aqui
FLASK_ENV=production
DATABASE_URL=sqlite:///dental.db
UPLOAD_FOLDER=/opt/clinic/uploads
MAX_CONTENT_LENGTH=536870912
```

---

## 👤 Credenciais Padrão

| Campo | Valor |
|---|---|
| Utilizador | `admin` |
| Senha | `admin` |
| Perfil | Superadministrador |

> ⚠️ **Altere a senha imediatamente após o primeiro acesso.**

---

## 📋 Perfis de Acesso (RBAC)

| Perfil | Permissões |
|---|---|
| **Superadmin** | Acesso total, painel de sistema, backups |
| **Diretor Clínico** | Gestão clínica, utilizadores, auditoria, relatórios |
| **Dentista** | Sessões, odontograma, prescrições, Rx |
| **Receção** | Agendamentos, pacientes, check-in |
| **Paciente** | Portal pessoal com acesso aos seus dados |

---

## 🗂 Estrutura do Projeto

```
dental-clinic/
├── app/
│   ├── models.py          # Modelos da base de dados
│   ├── __init__.py        # Factory e migrações automáticas
│   ├── patients/          # Módulo de pacientes
│   ├── sessions/          # Módulo de sessões clínicas
│   ├── scheduling/        # Agenda e agendamentos
│   ├── stock/             # Armazém e stock
│   ├── superadmin/        # Painel de administração
│   └── templates/         # Templates Jinja2
├── translations/          # Ficheiros de tradução (PT/EN/ES)
├── uploads/               # Ficheiros enviados
├── run.py                 # Ponto de entrada
├── requirements.txt       # Dependências Python
└── install.sh             # Instalador Ubuntu Server
```

---

## 🔄 Gestão do Serviço (após instalação)

```bash
# Ver estado
systemctl status dental-clinic

# Ver logs em tempo real
journalctl -u dental-clinic -f

# Reiniciar
systemctl restart dental-clinic

# Atualizar para nova versão
cd /opt/dental-clinic
git pull
systemctl restart dental-clinic
```

---

## 💾 Backup

O painel Superadmin inclui backup/restauro via browser (ZIP com base de dados + uploads).

Para backup automático via linha de comandos:

```bash
# Backup manual
zip -r backup_$(date +%Y%m%d).zip instance/dental.db uploads/

# Agendar com cron (diário às 02:00)
echo "0 2 * * * root zip -r /backups/dental_\$(date +\%Y\%m\%d).zip /opt/dental-clinic/instance/dental.db /opt/dental-clinic/uploads/" >> /etc/crontab
```

---

## 🛡 Segurança em Produção

```bash
# Instalar Certbot para HTTPS (recomendado)
apt install certbot python3-certbot-nginx
certbot --nginx -d seu-dominio.com
```

---

## 📦 Tecnologias

- **Backend:** Python 3.11, Flask 3, SQLAlchemy, Flask-Login, Flask-Babel
- **Frontend:** Bootstrap 5, Bootstrap Icons, FullCalendar.js
- **Base de dados:** SQLite (produção leve) — migrável para PostgreSQL
- **PDF:** ReportLab
- **Monitorização:** psutil
- **Autenticação:** Flask-Login + CSRF (Flask-WTF)

---

## 📄 Licença

MIT License — livre para uso comercial e modificação.
