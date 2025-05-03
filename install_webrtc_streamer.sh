#!/bin/bash

set -euo pipefail

# === Настройки ===
APP_NAME="WebRTC Streamer"
APP_DIR="/opt/webrtc-streamer"
SERVICE_NAME="webrtc-streamer"
ARCHIVE_URL="https://github.com/mpromonet/webrtc-streamer/releases/download/v0.8.11/webrtc-streamer-v0.8.11-Linux-x86_64-Release.tar.gz"
REQUIRED_PACKAGES=("wget" "curl" "ffmpeg" "v4l-utils" "git" "build-essential" "cmake" "libnsl2" "libsm6")
DEBUG=${DEBUG:-0}

# === Цвета для вывода ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# === Функции ===
log() {
    echo -e "${GREEN}[INFO] $1${NC}" >&2
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}" >&2
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
    exit 1
}

cleanup() {
    if [ -d "$TMPDIR" ]; then
        log "Очистка временных файлов..."
        rm -rf "$TMPDIR"
    fi
}

trap cleanup EXIT

# === Проверка запуска от root ===
if [ "$(id -u)" -ne 0 ]; then
    error "Скрипт должен быть запущен от root. Используйте sudo."
fi

# === Проверка systemd ===
if ! command -v systemctl >/dev/null 2>&1; then
    error "systemctl не найден. Поддерживаются только системы с systemd."
fi

# === Проверка наличия curl/wget ===
check_network_tools() {
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        error "Не найдено ни curl, ни wget. Установите один из них."
    fi
}

# === Запрос RTSP-ссылки ===
get_rtsp_url() {
    if [ -n "${RTSP_URL:-}" ]; then
        return 0
    fi

    while true; do
        read -rp "🔗 Введите ссылку на RTSP-поток (например, rtsp://user:pass@192.168.0.33:554): " RTSP_URL
        if [[ "$RTSP_URL" =~ ^rtsp:// ]]; then
            break
        else
            warn "Некорректный формат ссылки. Должно начинаться с rtsp://"
        fi
    done
}

# === Обновление системы ===
update_system() {
    log "Обновление системы..."
    apt update -y #&& apt upgrade -y
}

# === Установка зависимостей ===
install_dependencies() {
    log "Установка зависимостей..."
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! dpkg -l | grep -q "$package"; then
            apt install -y "$package" || error "Не удалось установить $package"
        fi
    done
}

# === Скачивание архива ===
download_archive() {
    log "Скачивание архива..."
    cd "$TMPDIR"
    
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_NAME"
    else
        wget -O "$ARCHIVE_NAME" "$ARCHIVE_URL"
    fi
    
    if [ ! -f "$ARCHIVE_NAME" ]; then
        error "Не удалось скачать архив"
    fi
}

# === Проверка существующей установки ===
check_existing_install() {
    if [ -f "$APP_DIR/webrtc-streamer" ]; then
        warn "Обнаружена существующая установка в $APP_DIR"
        read -rp "Удалить и переустановить? [y/N] " response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            systemctl stop "$SERVICE_NAME" || true
            systemctl disable "$SERVICE_NAME" || true
            rm -rf "$APP_DIR"
            log "Старая установка удалена"
        else
            error "Установка прервана пользователем"
        fi
    fi
}

# === Основная логика ===
main() {
    TMPDIR=$(mktemp -d)
    ARCHIVE_NAME="${ARCHIVE_URL##*/}"
    
    check_network_tools
    check_existing_install
    get_rtsp_url
    update_system
    install_dependencies
    download_archive
    
    log "Распаковка архива..."
    tar -xf "$ARCHIVE_NAME" || error "Не удалось распаковать архив"
    
    log "Создание директорий..."
    mkdir -p "$APP_DIR"
    
    log "Копирование файлов..."
    cp -r webrtc-streamer*/share/webrtc-streamer/* "$APP_DIR/"
    cp webrtc-streamer*/bin/webrtc-streamer "$APP_DIR/"
    chmod +x "$APP_DIR/webrtc-streamer"
    
    log "Создание конфигурации..."
    cat > "$APP_DIR/config.json" <<EOF
{
  "urls": {
    "CamHome1": {
      "video": "$RTSP_URL"
    }
  }
}
EOF

    log "Создание systemd сервиса..."
    cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=WebRTC Streamer Service
After=network.target

[Service]
ExecStart=$APP_DIR/webrtc-streamer -C $APP_DIR/config.json
WorkingDirectory=$APP_DIR
Restart=always
User=webrtc
Group=webrtc
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

    # Создание пользователя
    if ! id "webrtc" >/dev/null 2>&1; then
        useradd -r -s /bin/false -m -d "$APP_DIR" webrtc || warn "Не удалось создать пользователя"
    fi
    
    chown -R webrtc:webrtc "$APP_DIR"
    
    log "Перезагрузка systemd..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"
    
    log "Проверка статуса сервиса..."
    systemctl status "$SERVICE_NAME" --no-pager
    
    echo -e "\n✅ Установка завершена!"
    echo "Откройте в браузере: http://<IP-адрес>:8000/webrtcstreamer.html?video=CamHome1"
    echo "ℹ️ Замените <IP-адрес> на адрес сервера"
    echo "⚠️ Убедитесь, что порт 8000 открыт в фаерволе"
}

# === Запуск ===
main "$@"
