#!/bin/sh
set -e

DEBUG=1
SCRIPT_URL="https://raw.githubusercontent.com/vladus80/Scripts/main/testscript.sh"

# Безопасный вывод отладки — только как комментарий
debug() {
  [ "$DEBUG" = "1" ] && echo "# $@"
}

# Скачивание скрипта
if command -v curl >/dev/null 2>&1; then
  debug "Скачиваем с помощью curl"
  curl -fsSL "$SCRIPT_URL"
elif command -v wget >/dev/null 2>&1; then
  debug "Скачиваем с помощью wget"
  wget -qO- "$SCRIPT_URL"
elif command -v fetch >/dev/null 2>&1; then
  debug "Скачиваем с помощью fetch"
  fetch -o - "$SCRIPT_URL"
elif command -v python3 >/dev/null 2>&1; then
  debug "Скачиваем с помощью python3"
  python3 -c "import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1]).read().decode(), end='')" "$SCRIPT_URL"
else
  echo "# Ошибка: не найдено ни curl, ни wget, ни fetch, ни python3." >&2
  exit 1
fi | sh
