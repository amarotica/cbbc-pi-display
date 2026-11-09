#!/usr/bin/env bash
# Launched inside the existing labwc session by its autostart file.
set -euo pipefail
: "${WAYLAND_DISPLAY:?Run this launcher from the labwc desktop session}"
: "${XDG_RUNTIME_DIR:?No graphical user runtime directory}"
socket_path=$WAYLAND_DISPLAY
[[ $socket_path = /* ]] || socket_path="$XDG_RUNTIME_DIR/$socket_path"
# labwc -m can run both user and system autostart files; prevent duplicates.
exec 9>"$XDG_RUNTIME_DIR/cbbc-signage.lock"
flock -n 9 || exit 0
export QT_QPA_PLATFORM=wayland
export QT_WAYLAND_SHELL_INTEGRATION=xdg-shell
export QT_WAYLAND_DISABLE_WINDOWDECORATION=1
export QT_AUTO_SCREEN_SCALE_FACTOR=0
export QT_SCALE_FACTOR=1
cd /opt/cbbc-signage
# Let normal desktop startup finish, then stop its existing idle blanker.
# Future user swayidle autostarts are disabled (and backed up) by setup.sh.
sleep 2
pkill -u "$(id -u)" -x swayidle || true
while [[ -S $socket_path ]]; do
    systemd-cat --identifier=cbbc-signage-viewer \
        /opt/cbbc-signage/.venv/bin/python -m signage.viewer || true
    sleep 3
done
