#!/usr/bin/env bash
# Single-step install: pip brings Pillow + bundled ffmpeg.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> pip install ercomp (editable)"
python3 -m pip install -e "${ROOT}" --break-system-packages 2>/dev/null \
  || python3 -m pip install -e "${ROOT}"

mkdir -p "${HOME}/.local/bin"
cat > "${HOME}/.local/bin/ercomp" << EOF
#!/usr/bin/env bash
exec python3 -m ercomp "\$@"
EOF
chmod +x "${HOME}/.local/bin/ercomp"

echo "==> done"
python3 -m ercomp doctor || true
echo "run: ercomp <file>"
