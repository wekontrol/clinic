#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║         DentClinic — Instalador Ubuntu Server               ║
# ║         Testado em Ubuntu 22.04 LTS / 24.04 LTS             ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

APP_NAME="dental-clinic"
APP_DIR="/opt/dental-clinic"
APP_USER="dental"
APP_PORT="5000"
PYTHON="python3"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }

# ── Root check ────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Execute como root: sudo bash install.sh"

info "════════════════════════════════════════════"
info "  DentClinic — Instalação automática"
info "════════════════════════════════════════════"

# ── Dependências do sistema ───────────────────────────────────
info "Actualizando pacotes do sistema..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx curl git 2>/dev/null
info "Pacotes instalados."

# ── Utilizador dedicado ───────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    info "Utilizador '$APP_USER' criado."
fi

# ── Directório da aplicação ───────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$SCRIPT_DIR" != "$APP_DIR" ]; then
    info "Copiando aplicação para $APP_DIR ..."
    mkdir -p "$APP_DIR"
    cp -r "$SCRIPT_DIR"/. "$APP_DIR/"
fi

mkdir -p "$APP_DIR/instance" "$APP_DIR/uploads"

# ── Ambiente virtual Python ───────────────────────────────────
info "Criando ambiente virtual Python..."
$PYTHON -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
info "Dependências Python instaladas."

# ── Ficheiro de ambiente (.env) ───────────────────────────────
ENV_FILE="$APP_DIR/instance/.env"
if [ ! -f "$ENV_FILE" ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "$ENV_FILE" <<EOF
SECRET_KEY=${SECRET}
FLASK_ENV=production
DATABASE_URL=sqlite:///$(realpath "$APP_DIR/instance/dental.db")
UPLOAD_FOLDER=${APP_DIR}/uploads
MAX_CONTENT_LENGTH=536870912
EOF
    info ".env criado em $ENV_FILE"
else
    warn ".env já existe — não foi substituído."
fi

# ── Permissões ────────────────────────────────────────────────
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod -R 750 "$APP_DIR"
chmod 640 "$ENV_FILE"

# ── Inicializar base de dados ─────────────────────────────────
info "Inicializando base de dados..."
cd "$APP_DIR"
sudo -u "$APP_USER" bash -c "
  set -a; source '$ENV_FILE'; set +a
  '$APP_DIR/venv/bin/python' -c 'from app import create_app; app = create_app(); print(\"DB OK\")'
"

# ── Serviço systemd ───────────────────────────────────────────
info "Configurando serviço systemd..."
cat > /etc/systemd/system/dental-clinic.service <<EOF
[Unit]
Description=DentClinic — Sistema de Gestão Clínica
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${APP_DIR}/venv/bin/python run.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dental-clinic

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable dental-clinic
systemctl restart dental-clinic
info "Serviço dental-clinic iniciado."

# ── Nginx reverse proxy ───────────────────────────────────────
info "Configurando Nginx..."
cat > /etc/nginx/sites-available/dental-clinic <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 512M;

    location /uploads/ {
        alias ${APP_DIR}/uploads/;
        expires 7d;
    }

    location / {
        proxy_pass         http://127.0.0.1:${APP_PORT};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/dental-clinic /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
info "Nginx configurado."

# ── Resumo final ──────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓  DentClinic instalado com sucesso!            ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  URL:      http://${IP}                          ${NC}"
echo -e "${GREEN}║  Login:    admin                                 ${NC}"
echo -e "${GREEN}║  Senha:    admin  (altere após o 1.º acesso!)    ${NC}"
echo -e "${GREEN}║                                                  ${NC}"
echo -e "${GREEN}║  Logs:     journalctl -u dental-clinic -f        ${NC}"
echo -e "${GREEN}║  Status:   systemctl status dental-clinic        ${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
