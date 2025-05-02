#!/bin/sh
set -e

DEBUG=1
BASE_URL="https://raw.githubusercontent.com/vladus80/Scripts/main"

# Функция вывода отладки
debug() {
  [ "$DEBUG" = "1" ] && echo "# $@" >&2
}

# Парсинг аргументов
SCRIPT_NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    -script)
      SCRIPT_NAME="$2"
      shift 2
      ;;
    -d|--debug)
      DEBUG=1
      shift
      ;;
    *)
      echo "Неизвестный параметр: $1" >&2
      exit 1
      ;;
  esac
done

# Проверка, задан ли скрипт
if [ -z "$SCRIPT_NAME" ]; then
  echo "Использование: $0 -script имя_скрипта.sh" >&2
  exit 1
fi

SCRIPT_URL="$BASE_URL/$SCRIPT_NAME"
debug "Скачиваем и исполняем: $SCRIPT_URL"

# Загрузка и исполнение
if command -v curl >/dev/null 2>&1; then
  debug "curl используется для загрузки"
  curl -fsSL "$SCRIPT_URL"
elif command -v wget >/dev/null 2>&1; then
  debug "wget используется для загрузки"
  wget -qO- "$SCRIPT_URL"
elif command -v fetch >/dev/null 2>&1; then
  debug "fetch используется для загрузки"
  fetch -o - "$SCRIPT_URL"
elif command -v python3 >/dev/null 2>&1; then
  debug "python3 используется для загрузки"
  python3 -c "import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1]).read().decode(), end='')" "$SCRIPT_URL"
else
  echo "Ошибка: не найдено curl/wget/fetch/python3" >&2
  exit 1
fi | sh
