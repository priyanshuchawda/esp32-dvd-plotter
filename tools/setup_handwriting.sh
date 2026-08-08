#!/usr/bin/env bash
# Fetch the neural handwriting model and build an isolated environment for it.
#
# This lives outside the repo tree in ext/ because the checkpoints are ~60 MB
# and torch is far larger. Everything it creates is gitignored, so deleting
# ext/ and rerunning this script is a clean reset.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT="$REPO_ROOT/ext"
TOOLKIT="$EXT/handwriting-synthesis"
VENV="$EXT/venv"
UPSTREAM="https://github.com/X-rayLaser/pytorch-handwriting-synthesis-toolkit.git"

mkdir -p "$EXT"

if [ -d "$TOOLKIT/.git" ]; then
    echo "toolkit already present at $TOOLKIT"
else
    echo "cloning handwriting toolkit..."
    git clone --depth 1 "$UPSTREAM" "$TOOLKIT"
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is required. See https://docs.astral.sh/uv/" >&2
    exit 1
fi

# The toolkit pins torch<2, but it runs fine on current torch; only the CPU
# build is needed since the model is small enough to sample in seconds.
echo "building environment at $VENV..."
uv venv -p 3.11 "$VENV"
uv pip install --python "$VENV/bin/python" torch \
    --index-url https://download.pytorch.org/whl/cpu
uv pip install --python "$VENV/bin/python" "numpy<2" "Pillow<10" matplotlib svgwrite h5py

echo
echo "done. Try:"
echo "  $VENV/bin/python tools/handwriting2gcode.py 'hello world' -o hello.gcode"
