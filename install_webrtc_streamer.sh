#!/bin/bash

set -euo pipefail

# === Проверка запуска от root ===
if [ "$(id -u)" -ne 0 ]; then
  echo "❌ Скрипт должен быть запущен от root."
  exit 1
fi

# === Проверка наличия systemctl ===
if ! command -v systemctl >/dev/null 2>&1; then
  echo "❌ systemctl не найден. Поддерживается только systemd-системы."
  exit 1
fi

# === Запрос RTSP-ссылки ===
echo "🔗 Введите ссылку на RTSP-поток (например, rtsp://user:pass@192.168.0.33:554):"
read -r RTSP_URL

if [ -z "$RTSP_URL" ]; then
  echo "❌ Ссылка не может быть пустой!"
  exit 1
fi

# === Параметры ===
APP_DIR="/opt/webrtc-streamer"
TMPDIR=$(mktemp -d)
ARCHIVE_URL="https://github.com/mpromonet/webrtc-streamer/releases/download/v0.8.11/webrtc-streamer-v0.8.11-Linux-x86_64-Release.tar.gz"
ARCHIVE_NAME="${ARCHIVE_URL##*/}"

# === 1. Обновление системы ===
echo "=== 1. Обновление пакетов ==="
apt update
apt install -y wget curl ffmpeg v4l-utils git build-essential cmake libnsl2 libsm6 mc htop

# === 2. Скачивание и распаковка ===
echo "=== 2. Скачивание WebRTC Streamer ==="
cd "$TMPDIR"
wget "$ARCHIVE_URL"
tar -xf "$ARCHIVE_NAME"

# === 3. Установка в $APP_DIR ===
echo "=== 3. Установка в $APP_DIR ==="
mkdir -p "$APP_DIR"
cp -r webrtc-streamer*/share/webrtc-streamer/* "$APP_DIR/"
cp webrtc-streamer*/bin/webrtc-streamer "$APP_DIR/"
chmod +x "$APP_DIR/webrtc-streamer"

# === 4. Создание config.json ===
echo "=== 4. Создание конфигурации ==="
cat > "$APP_DIR/config.json" <<EOF
{
  "urls": {
    "CamHome1": {
      "video": "$RTSP_URL"
    }
  }
}
EOF

# === 5. Создание systemd сервиса ===
echo "=== 5. Создание systemd сервиса ==="
cat > /etc/systemd/system/webrtc-streamer.service <<EOF
[Unit]
Description=WebRTC Streamer Service
After=network.target

[Service]
ExecStart=$APP_DIR/webrtc-streamer -C $APP_DIR/config.json
WorkingDirectory=$APP_DIR
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

# === 6. Запуск и включение сервиса ===
echo "=== 6. Активация systemd-сервиса ==="
systemctl daemon-reexec
systemctl enable webrtc-streamer
systemctl start webrtc-streamer

# === 7. Очистка временных файлов ===
rm -rf "$TMPDIR"

# === 8. Проверка статуса ===
echo "=== 7. Статус сервиса ==="
systemctl status webrtc-streamer --no-pager

# === Завершение ===
echo "✅ Установка завершена!"
echo "Открой в браузере:"
echo "http://<IP-адрес>:8000/webrtcstreamer.html?video=CamHome1"
echo "ℹ️ Замените <IP-адрес> на адрес сервера."
