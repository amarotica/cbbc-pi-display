#!/usr/bin/env bash
# Install on Raspberry Pi OS 64-bit. Run: sudo bash setup.sh [--user USER]
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
    echo 'Run with sudo: sudo bash setup.sh [--user USER]' >&2
    exit 1
fi
target_user=${SUDO_USER:-}
while (($#)); do
    case "$1" in
        --user) [[ $# -ge 2 ]] || { echo 'Missing --user value' >&2; exit 1; }; target_user=$2; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done
if [[ ! $target_user =~ ^[a-z_][a-z0-9_-]*\$?$ || $target_user == root ]] || ! id "$target_user" &>/dev/null; then
    echo 'Specify an existing non-root account with --user USER (or run from that account using sudo).' >&2
    exit 1
fi
if [[ $(dpkg --print-architecture) != arm64 ]]; then
    echo 'This installer requires Raspberry Pi OS 64-bit (arm64), Bookworm or Trixie.' >&2
    exit 1
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install_dir=/opt/cbbc-signage
config_dir=/etc/cbbc-signage
cache_dir=/var/lib/cbbc-signage
# Check hostname before changing a fresh installation.
if [[ ! -f $config_dir/config.json && ! $(hostname -s) =~ ^(lmt|mfr)-pi-[0-9]+$ ]]; then
    echo 'Set the hostname to lmt-pi-N or mfr-pi-N before installing.' >&2
    echo 'Example: sudo hostnamectl set-hostname lmt-pi-1' >&2
    exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pyqt5 python3-pil \
    xserver-xorg x11-xserver-utils x11-utils lightdm openbox dbus-x11 fonts-dejavu-core

systemctl stop cbbc-signage-updater.service 2>/dev/null || true
install -d "$install_dir/signage" "$install_dir/bin" "$install_dir/systemd" "$config_dir" "$cache_dir"
# Copy explicit files, so updating from the installed directory is safe too.
if [[ $source_dir != "$install_dir" ]]; then
    install -m 644 "$source_dir"/signage/*.py "$install_dir/signage/"
    install -m 644 "$source_dir/requirements.txt" "$install_dir/requirements.txt"
    install -m 755 "$source_dir/bin/session.sh" "$install_dir/bin/session.sh"
    install -m 644 "$source_dir/systemd/cbbc-signage-updater.service" "$install_dir/systemd/"
    install -m 644 "$source_dir/config.example.json" "$install_dir/config.example.json"
fi
if [[ ! -f $config_dir/config.json ]]; then
    install -m 644 "$source_dir/config.example.json" "$config_dir/config.json"
fi
python3 -m venv --system-site-packages "$install_dir/.venv"
"$install_dir/.venv/bin/python" -m pip install --disable-pip-version-check -r "$install_dir/requirements.txt"
# A matched browser is installed once; ordinary updates never need to download it.
PLAYWRIGHT_BROWSERS_PATH="$install_dir/browsers" \
    "$install_dir/.venv/bin/python" -m playwright install --with-deps chromium
chmod -R a+rX "$install_dir/browsers"
chown -R "$target_user:$(id -gn "$target_user")" "$cache_dir"
cd "$install_dir"
"$install_dir/.venv/bin/python" -c 'from signage.common import load_config; load_config("/etc/cbbc-signage/config.json")'

install -d /usr/share/xsessions /etc/lightdm/lightdm.conf.d
cat > /usr/share/xsessions/cbbc-signage.desktop <<'EOF'
[Desktop Entry]
Name=Common Block Signage
Comment=Offline-capable food and drinks displays
Exec=/opt/cbbc-signage/bin/session.sh
Type=Application
EOF
cat > /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf <<EOF
[Seat:*]
autologin-user=$target_user
autologin-user-timeout=0
autologin-session=cbbc-signage
user-session=cbbc-signage
xserver-command=X -s 0 -dpms -nocursor
EOF
sed "s/@USER@/$target_user/g" "$source_dir/systemd/cbbc-signage-updater.service" \
    > /etc/systemd/system/cbbc-signage-updater.service
systemctl daemon-reload
systemctl enable --now cbbc-signage-updater.service
# Select LightDM even when installed over an existing desktop display manager.
printf '%s\n' /usr/sbin/lightdm > /etc/X11/default-display-manager
systemctl enable lightdm.service --force
systemctl set-default graphical.target
echo
echo "Installed for $target_user on $(hostname -s). Config: $config_dir/config.json"
echo 'Connect both displays, then run: sudo reboot'
echo 'The first successful fetch is needed before a menu can be displayed offline.'
