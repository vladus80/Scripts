#!/bin/bash

set -euo pipefail

###############################################################################
# 🛰️ Установщик WebRTC Streamer
#
# 📦 Назначение:
#   Этот скрипт устанавливает WebRTC Streamer от mpromonet:
#   - скачивает бинарник;
#   - создаёт конфигурацию с вашей RTSP-ссылкой;
#   - устанавливает как systemd-сервис под отдельным пользователем `webrtc`.
#
# 🧰 Зависимости: apt, curl или wget, systemd
#
# 🧾 Поддерживаемые параметры:
#   -url=<rtsp://...>     — передать ссылку RTSP в аргументе
#   RTSP_URL=<...>        — (переменная окружения) тоже можно передать ссылку
#
# 🔧 Пример запуска:
#   RTSP_URL="rtsp://admin:pass@192.168.0.33:554" ./install_webrtc_streamer.sh
#   ./install_webrtc_streamer.sh -url=rtsp://admin:pass@192.168.0.33:554
#
# 📄 Скачать и установить:
# wget https://raw.githubusercontent.com/vladus80/Scripts/refs/heads/main/install_webrtc_streamer.sh
# chmod +x install_webrtc_streamer.sh
# ./install_webrtc_streamer.sh
# ------------------------------------------------------------------------------
# Просмотр:
#   http://<IP>:8000/webrtcstreamer.html?video=CamHome1
###############################################################################

# === Конфигурация ===
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

# === Функции логирования ===
log() { echo -e "${GREEN}[INFO] $1${NC}" >&2; }
warn() { echo -e "${YELLOW}[WARN] $1${NC}" >&2; }
error() { echo -e "${RED}[ERROR] $1${NC}" >&2; exit 1; }

# === Очистка временных файлов ===
cleanup() {
    if [ -d "${TMPDIR:-}" ]; then
        log "Очистка временных файлов..."
        rm -rf "$TMPDIR"
    fi
}
trap cleanup EXIT

# === Проверка запуска от root ===
if [ "$(id -u)" -ne 0 ]; then
    error "Скрипт должен быть запущен от root. Используйте sudo."
fi

# === Проверка наличия systemd ===
if ! command -v systemctl >/dev/null 2>&1; then
    error "systemctl не найден. Поддерживаются только systemd-системы."
fi

# === Проверка curl или wget ===
check_network_tools() {
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        error "Не найдено ни curl, ни wget. Установите один из них."
    fi
}

# === Обработка параметров командной строки (например, -url=...) ===
for arg in "$@"; do
    case "$arg" in
        -url=*)
            RTSP_URL="${arg#*=}"
            ;;
        -h|--help)
            grep '^#' "$0" | cut -c 3-
            exit 0
            ;;
    esac
done

# === Запрос RTSP-ссылки, если не передана ===
get_rtsp_url() {
    if [ -n "${RTSP_URL:-}" ]; then return; fi

    while true; do
        read -rp "🔗 Введите ссылку на RTSP-поток (например, rtsp://user:pass@192.168.0.33:554): " RTSP_URL
        if [[ "$RTSP_URL" =~ ^rtsp:// ]]; then break
        else warn "Некорректный формат ссылки. Должно начинаться с rtsp://"
        fi
    done
}

# === Обновление и установка зависимостей ===
update_system() {
    log "Обновление списка пакетов..."
    apt update -y
}

install_dependencies() {
    log "Установка зависимостей..."
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! dpkg -l | grep -qw "$package"; then
            apt install -y "$package" || error "Не удалось установить $package"
        fi
    done
}

# === Скачивание архива ===
download_archive() {
    log "Скачивание архива..."
    cd "$TMPDIR"
    if command -v curl >/dev/null; then
        curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_NAME"
    else
        wget -O "$ARCHIVE_NAME" "$ARCHIVE_URL"
    fi
    [ -f "$ARCHIVE_NAME" ] || error "Архив не скачан"
}

# === Проверка существующей установки ===
check_existing_install() {
    if [ -f "$APP_DIR/webrtc-streamer" ]; then
        warn "Уже установлено в $APP_DIR"
        read -rp "Удалить и переустановить? [y/N] " resp
        if [[ "$resp" =~ ^[yY](es)?$ ]]; then
            systemctl stop "$SERVICE_NAME" || true
            systemctl disable "$SERVICE_NAME" || true
            rm -rf "$APP_DIR"
            log "Старая установка удалена"
        else
            error "Установка отменена"
        fi
    fi
}

# === Основной процесс установки ===
main() {
    TMPDIR=$(mktemp -d)
    ARCHIVE_NAME="${ARCHIVE_URL##*/}"

    check_network_tools
    check_existing_install
    get_rtsp_url
    update_system
    install_dependencies
    download_archive

    log "Распаковка..."
    tar -xf "$ARCHIVE_NAME" || error "Ошибка распаковки"

    log "Копирование файлов в $APP_DIR..."
    mkdir -p "$APP_DIR"
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

    log "Создание systemd-сервиса..."
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

[Install]
WantedBy=multi-user.target
EOF

    if ! id "webrtc" >/dev/null 2>&1; then
        useradd -r -s /usr/sbin/nologin -d "$APP_DIR" webrtc || warn "Не удалось создать пользователя"
    fi
    chown -R webrtc:webrtc "$APP_DIR"

    log "Активация сервиса..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"

    log "Проверка статуса:"
    systemctl status "$SERVICE_NAME" --no-pager

    echo -e "\n✅ Установка завершена!"
    echo "🌐 Откройте: http://<IP>:8000/webrtcstreamer.html?video=CamHome1"
    echo "ℹ️ Замените <IP> на адрес сервера. Проверьте, что порт 8000 открыт."
    echo "ℹ️ При необходимости добавьте камеры в /opt/webrtc-streamer/config.json"
}

# === Запуск ===
main "$@"
