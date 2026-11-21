#!/usr/bin/env bash
# One-time setup for a fresh session: Python packages, ffmpeg check, videos branch checkout.
set -e
cd "$(dirname "$0")"
python3 -c "import PIL, numpy, scipy" 2>/dev/null || pip install --quiet --break-system-packages pillow numpy scipy
command -v ffmpeg >/dev/null || { (apt-get install -y -qq ffmpeg >/dev/null 2>&1) || { echo "ffmpeg is missing and could not be installed"; exit 1; }; }
mkdir -p out
python3 tools/reelq.py sync
echo "ready"
