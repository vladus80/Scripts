#!/bin/sh
set -e

SCRIPT_URL="https://raw.githubusercontent.com/vladus80/Scripts/main/testscript.sh"

# Попытаться использовать curl, wget или sh + /dev/tcp
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$SCRIPT_URL"
#elif command -v wget >/dev/null 2>&1; then
  #wget -O- "$SCRIPT_URL"
elif command -v fetch >/dev/null 2>&1; then
  fetch -o - "$SCRIPT_URL"
elif command -v python3 >/dev/null 2>&1; then
  python3 -c "import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1]).read().decode(), end='')" "$SCRIPT_URL"
else
  echo "Ошибка: не найдено ни curl, ни wget, ни fetch, ни python3." >&2
  exit 1
fi | sh
