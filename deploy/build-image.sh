#!/usr/bin/env bash
# Собирает образ cargo-assistant с версией, равной короткому хэшу коммита.
# Использование: deploy/build-image.sh [реестр/имя]; по умолчанию имя cargo-assistant.
set -euo pipefail

cd "$(dirname "$0")/.."

NAME="${1:-cargo-assistant}"
VERSION="$(git rev-parse --short HEAD)"
if [ -n "$(git status --porcelain)" ]; then
  VERSION="${VERSION}-dirty"
fi

docker build --build-arg "APP_VERSION=${VERSION}" -t "${NAME}:${VERSION}" .
echo "Собран образ ${NAME}:${VERSION}"
