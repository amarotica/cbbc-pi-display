#!/usr/bin/env bash
set -eu
export QT_QPA_PLATFORM=xcb
export QT_AUTO_SCREEN_SCALE_FACTOR=0
export QT_SCALE_FACTOR=1
cd /opt/cbbc-signage
xset s off
xset s noblank
xset -dpms
xsetroot -solid black
openbox &
wm_pid=$!
trap 'kill "$wm_pid" 2>/dev/null || true' EXIT
# LightDM restarts the session if it exits; keep retrying transient viewer errors.
while true; do
    /opt/cbbc-signage/.venv/bin/python -m signage.viewer || true
    sleep 3
done
