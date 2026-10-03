#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -f results/latest/replay.json ]; then ./run.sh; fi
printf '\nOpen http://127.0.0.1:8766/viewer/\nLocal replay only; no public deployment.\n\n'
exec python3 -m http.server 8766 --bind 127.0.0.1
