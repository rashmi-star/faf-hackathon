#!/usr/bin/env bash
# Fetch the Inter typeface (SIL Open Font License) for burned-in text rendering.
#
# Downloads the official Inter release zip and installs the static TTF weights
# the edit engine uses (Regular for captions/lower-thirds, SemiBold for titles)
# plus the OFL license into agent/assets/fonts/. Idempotent: skips the download
# when the fonts are already present.
#
# Usage: scripts/fetch_fonts.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FONT_DIR="$REPO_ROOT/agent/assets/fonts"
INTER_VERSION="4.1"
INTER_URL="https://github.com/rsms/inter/releases/download/v${INTER_VERSION}/Inter-${INTER_VERSION}.zip"

if [[ -f "$FONT_DIR/Inter-Regular.ttf" && -f "$FONT_DIR/Inter-SemiBold.ttf" ]]; then
  echo "Inter already installed in $FONT_DIR — nothing to do."
  exit 0
fi

mkdir -p "$FONT_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Downloading Inter v${INTER_VERSION}..."
curl -fsSL --retry 3 -o "$TMP_DIR/inter.zip" "$INTER_URL"

# The release zip ships static TTFs under extras/ttf/.
unzip -q -o "$TMP_DIR/inter.zip" -d "$TMP_DIR/inter" \
  "extras/ttf/Inter-Regular.ttf" "extras/ttf/Inter-SemiBold.ttf" "LICENSE.txt"

cp "$TMP_DIR/inter/extras/ttf/Inter-Regular.ttf" "$FONT_DIR/Inter-Regular.ttf"
cp "$TMP_DIR/inter/extras/ttf/Inter-SemiBold.ttf" "$FONT_DIR/Inter-SemiBold.ttf"
cp "$TMP_DIR/inter/LICENSE.txt" "$FONT_DIR/OFL-LICENSE.txt"

echo "Installed Inter Regular + SemiBold (OFL) into $FONT_DIR"
