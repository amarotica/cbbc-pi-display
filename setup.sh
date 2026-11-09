#!/usr/bin/env bash
# Reuse an existing Raspberry Pi OS Desktop labwc session.
# Run: sudo bash setup.sh [--user USER]
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
    echo 'This installer requires a 64-bit (arm64) Raspberry Pi desktop with labwc.' >&2
    exit 1
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install_dir=/opt/cbbc-signage
config_dir=/etc/cbbc-signage
cache_dir=/var/lib/cbbc-signage
target_home=$(getent passwd "$target_user" | cut -d: -f6)
if ! command -v labwc >/dev/null || ! command -v lightdm >/dev/null; then
    echo 'This installer reuses an existing labwc/LightDM desktop. Install Raspberry Pi OS Desktop first.' >&2
    exit 1
fi
desktop_session=$(python3 "$source_dir/signage/desktop_setup.py" --home "$target_home" --find-session)
desktop_args=()
labwc_command=$(pgrep -u "$(id -u "$target_user")" -a -x labwc || true)
if [[ $labwc_command =~ (^|[[:space:]])(-m|--merge-config)([[:space:]]|$) || $desktop_session == LXDE-pi-labwc || $desktop_session == rpd-labwc ]]; then
    desktop_args+=(--merge-config)
fi
# Check hostname before changing a fresh installation.
if [[ ! -f $config_dir/config.json && ! $(hostname -s) =~ ^(lmt|mfr)-pi-[0-9]+$ ]]; then
    echo 'Set the hostname to lmt-pi-N or mfr-pi-N before installing.' >&2
    echo 'Example: sudo hostnamectl set-hostname lmt-pi-1' >&2
    exit 1
fi
export DEBIAN_FRONTEND=noninteractive
browser_packages=()
if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
    browser_packages+=(chromium)
fi
apt-get update
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pyqt5 python3-pil qtwayland5 wlr-randr "${browser_packages[@]}"

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
# Reuse the desktop's system Chromium; no second browser or install-deps bundle.
chown -R "$target_user:$(id -gn "$target_user")" "$cache_dir"
cd "$install_dir"
"$install_dir/.venv/bin/python" -m signage.desktop_setup --migrate-config "$config_dir/config.json"
"$install_dir/.venv/bin/python" -c 'from signage.common import load_config; load_config("/etc/cbbc-signage/config.json")'
runuser -u "$target_user" -- "$install_dir/.venv/bin/python" -m signage.desktop_setup \
    --home "$target_home" "${desktop_args[@]}"

install -d /etc/lightdm/lightdm.conf.d
if [[ -f /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf && ! -f /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf.before-wayland ]]; then
    cp -p /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf.before-wayland
fi
cat > /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf <<EOF
[Seat:*]
autologin-user=$target_user
autologin-user-timeout=0
autologin-session=$desktop_session
EOF
# Retire only the previous installer's session entry, keeping a backup.
if [[ -f /usr/share/xsessions/cbbc-signage.desktop ]]; then
    mv /usr/share/xsessions/cbbc-signage.desktop /usr/share/xsessions/cbbc-signage.desktop.before-wayland
fi
# Raspberry Pi's own setting disables future desktop/greeter blanking as well.
if command -v raspi-config >/dev/null && [[ -n $labwc_command ]]; then
    SUDO_USER="$target_user" raspi-config nonint do_blanking 1
fi
sed "s/@USER@/$target_user/g" "$source_dir/systemd/cbbc-signage-updater.service" \
    > /etc/systemd/system/cbbc-signage-updater.service
systemctl daemon-reload
systemctl enable --now cbbc-signage-updater.service
systemctl enable lightdm.service
systemctl set-default graphical.target
echo
echo "Installed for $target_user on $(hostname -s). Config: $config_dir/config.json"
echo "Using existing Wayland desktop session: $desktop_session"
echo 'Connect both displays, then run: sudo reboot'
echo 'The first successful fetch is needed before a menu can be displayed offline.'
