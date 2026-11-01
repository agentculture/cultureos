#!/usr/bin/env bash
# Install arduino-flasher-cli (linux-arm64) into ~/.local/bin and verify `version`.
# Recovery prep only: this script never flashes or touches a board.
# Overrides (used by tests, no network needed): FLASHER_URL, FLASHER_SHA256,
# FLASHER_MIN_VERSION, INSTALL_DIR.
set -euo pipefail

VERSION="0.5.4"
DEFAULT_URL="https://github.com/arduino/arduino-flasher-cli/releases/download/v${VERSION}/arduino-flasher-cli-${VERSION}-linux-arm64.tar.gz"
# sha256 as published by the GitHub release asset digest for v0.5.4 linux-arm64
DEFAULT_SHA256="bb48d3c578a305fb42b8acc3e6f28f291b303468ad24432c5affc52ff3ecee38"

URL="${FLASHER_URL:-$DEFAULT_URL}"
SHA256="${FLASHER_SHA256:-$DEFAULT_SHA256}"
MIN_VERSION="${FLASHER_MIN_VERSION:-0.5.4}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

echo "Downloading $URL"
curl -fsSL "$URL" -o "$scratch/pkg.tar.gz"

actual="$(sha256sum "$scratch/pkg.tar.gz" | cut -d' ' -f1)"
if [ "$actual" != "$SHA256" ]; then
  echo "checksum mismatch: expected $SHA256, got $actual" >&2
  exit 1
fi

mkdir "$scratch/x"
tar -xzf "$scratch/pkg.tar.gz" -C "$scratch/x"
bin="$(find "$scratch/x" -type f -name arduino-flasher-cli | head -n1)"
if [ -z "$bin" ]; then
  echo "arduino-flasher-cli not found in archive" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
install -m 0755 "$bin" "$INSTALL_DIR/arduino-flasher-cli"

out="$("$INSTALL_DIR/arduino-flasher-cli" version)"
echo "$out"
found="$(printf '%s\n' "$out" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
lowest="$(printf '%s\n%s\n' "$MIN_VERSION" "$found" | sort -V | head -n1)"
if [ -z "$found" ] || [ "$lowest" != "$MIN_VERSION" ]; then
  echo "arduino-flasher-cli version '$found' is older than $MIN_VERSION" >&2
  rm -f "$INSTALL_DIR/arduino-flasher-cli"
  exit 1
fi
echo "OK: arduino-flasher-cli $found installed in $INSTALL_DIR"
