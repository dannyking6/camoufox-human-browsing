#!/usr/bin/env bash
# Idempotent installer for the camoufox-human-browsing stack.
# Debian/Ubuntu/Kali. Run as root or with sudo.
set -e

echo "==> System deps (Xvfb virtual display + screenshot tool)"
apt-get update -qq && apt-get install -y -qq xvfb imagemagick x11-utils

echo "==> Camoufox (anti-detect Firefox) + GeoIP coherence"
pip install --break-system-packages "camoufox[geoip]" || pip install "camoufox[geoip]"
python3 -m camoufox fetch

echo "==> HumanCursor (real human-like OS cursor)"
pip install --break-system-packages git+https://github.com/riflosnake/HumanCursor \
  || pip install git+https://github.com/riflosnake/HumanCursor

echo "==> Sanity imports"
python3 - <<'EOF'
from camoufox.async_api import AsyncCamoufox
from humancursor.system_cursor import SystemCursor
print("OK: camoufox + humancursor importable")
EOF

echo "==> Done. Test with:"
echo "    xvfb-run -a -s '-screen 0 1366x900x24' python3 scripts/human_test.py"
