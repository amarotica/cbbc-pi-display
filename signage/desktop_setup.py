"""Install a small autostart addition into an existing labwc desktop."""
import argparse
import configparser
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

BEGIN = "# BEGIN CBBC SIGNAGE"
END = "# END CBBC SIGNAGE"
BLOCK = f"{BEGIN}\n/opt/cbbc-signage/bin/session.sh &\n{END}\n"


def replace_text(path, content, mode=0o644):
    path = Path(path)
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".before-cbbc-signage")
        if not backup.exists():
            shutil.copy2(path, backup)
        mode = path.stat().st_mode & 0o777
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".cbbc-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def find_session(home, directory):
    candidates = {}
    for path in sorted(Path(directory).glob("*.desktop")):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read(path)
        command = parser.get("Desktop Entry", "Exec", fallback="")
        if re.search(r"\blabwc(?:-pi)?\b", command):
            candidates[path.stem] = path
    preferences = configparser.ConfigParser(interpolation=None, strict=False)
    preferences.read(Path(home) / ".dmrc")
    for name in (preferences.get("Desktop", "Session", fallback=""), "rpd-labwc", "LXDE-pi-labwc", "labwc"):
        if name in candidates:
            return name
    if candidates:
        return next(iter(candidates))
    raise ValueError("No installed labwc Wayland session found in /usr/share/wayland-sessions")


def install_autostart(home, system_autostart, merge_config=False):
    path = Path(home) / ".config/labwc/autostart"
    if path.exists():
        content = path.read_text()
    elif not merge_config and Path(system_autostart).exists():
        # Upstream non-merge labwc replaces system autostart with the user file.
        content = Path(system_autostart).read_text()
    else:
        # Pi's labwc -m runs system autostart separately; do not duplicate it.
        content = "#!/bin/sh\n"
    if (BEGIN in content) != (END in content):
        raise ValueError("Incomplete CBBC autostart markers; restore the autostart backup first")
    content = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "", content, flags=re.S)
    lines = []
    for line in content.splitlines(keepends=True):
        # This is the standard Pi desktop blanking command. Preserve it as a
        # comment as well as keeping the original file in a separate backup.
        if re.match(r"^\s*(?:/usr/bin/)?swayidle\b", line):
            line = "# CBBC disabled screen blanking: " + line
        lines.append(line)
    content = "".join(lines)
    # Put startup before any existing `exit` or `exec` in a user's script.
    first, _, rest = content.partition("\n")
    if content.startswith("#!"):
        content = first + "\n" + BLOCK + rest
    else:
        content = BLOCK + content
    replace_text(path, content, mode=0o755)
    path.chmod(path.stat().st_mode | 0o100)


def migrate_config(path, rotation=None):
    if rotation is not None and rotation not in {"normal", "left", "right", "inverted"}:
        raise ValueError("rotation must be normal, left, right, or inverted")
    path = Path(path)
    config = json.loads(path.read_text())
    changed = False
    for channel in config["channels"].values():
        output = channel.get("output")
        if output in {"HDMI-1", "HDMI-2"}:
            channel["output"] = output.replace("HDMI-", "HDMI-A-")
            changed = True
        if rotation is not None:
            if channel.get("rotation") != rotation:
                channel["rotation"] = rotation
                changed = True
            size = channel.get("viewport")
            if size and len(size) == 2:
                width, height = size
                portrait = rotation in {"left", "right"}
                if (portrait and width > height) or (not portrait and height > width):
                    channel["viewport"] = [height, width]
                    changed = True
    if changed:
        replace_text(path, json.dumps(config, indent=2) + "\n")
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--sessions-dir", type=Path, default=Path("/usr/share/wayland-sessions"))
    parser.add_argument("--system-autostart", type=Path, default=Path("/etc/xdg/labwc/autostart"))
    parser.add_argument("--find-session", action="store_true")
    parser.add_argument("--merge-config", action="store_true")
    parser.add_argument("--migrate-config", type=Path)
    parser.add_argument("--rotation", choices=("normal", "left", "right", "inverted"),
                        help="Set both channel rotations and orient their fallback viewports")
    args = parser.parse_args()
    if args.migrate_config:
        migrate_config(args.migrate_config, args.rotation)
    elif args.home is None:
        parser.error("--home is required")
    elif args.find_session:
        print(find_session(args.home, args.sessions_dir))
    else:
        install_autostart(args.home, args.system_autostart, args.merge_config)


if __name__ == "__main__":
    main()
