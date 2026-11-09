"""Configuration and crash-safe, content-addressed image storage."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from urllib.parse import urlsplit

from PIL import Image

from signage.display import output_name

CHANNELS = {"food": "food", "drinks": "drink"}


def load_config(path, hostname=None):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    location = config.get("location")
    if location is None:
        match = re.fullmatch(r"(lmt|mfr)-pi-\d+", (hostname or socket.gethostname()).split(".")[0].lower())
        if not match:
            raise ValueError("Hostname must be lmt-pi-N or mfr-pi-N, or set location in config")
        location = match[1]
    if location not in {"lmt", "mfr"}:
        raise ValueError("location must be lmt or mfr")
    config["location"] = location
    for key in ("poll_seconds", "timeout_seconds", "stable_seconds"):
        if not isinstance(config[key], (int, float)) or config[key] <= 0:
            raise ValueError(f"{key} must be positive")
    if config["settle_seconds"] < 0:
        raise ValueError("settle_seconds must be nonnegative")
    outputs = set()
    for name, slug in CHANNELS.items():
        channel = config["channels"][name]
        channel["output"] = output_name(channel["output"])
        if channel["output"] in outputs:
            raise ValueError("Food and drinks need distinct outputs")
        outputs.add(channel["output"])
        if channel.get("rotation", "normal") not in {"normal", "left", "right", "inverted"}:
            raise ValueError("Invalid output rotation")
        size = channel["viewport"]
        if len(size) != 2 or any(type(x) is not int or not 100 <= x <= 7680 for x in size):
            raise ValueError("viewport must contain two integer dimensions between 100 and 7680")
        channel.setdefault("url", f"https://commonblockbrewing.com/{location}-{slug}-specials/")
        if urlsplit(channel["url"]).scheme not in {"https", "http"}:
            raise ValueError("URL must be HTTP or HTTPS")
    return config


def atomic_write(path, data):
    """Flush data before atomic replacement; a failed write leaves the old file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, value):
    atomic_write(path, json.dumps(value, sort_keys=True).encode("utf-8"))


def pixel_hash(png):
    """Ignore PNG metadata/compression; only visible pixel changes count."""
    with Image.open(io.BytesIO(png)) as image:
        if image.format != "PNG" or image.width * image.height > 32_000_000:
            raise ValueError("Invalid or excessively large snapshot")
        image = image.convert("RGB")
        return hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()


class SnapshotStore:
    def __init__(self, root, location, channel):
        self.directory = Path(root) / location / channel
        self.manifest = self.directory / "current.json"

    def current(self):
        try:
            record = json.loads(self.manifest.read_text())
            digest = record["digest"]
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                return None
            png = (self.directory / f"{digest}.png").read_bytes()
            if pixel_hash(png) != digest:
                return None
            return record, png
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def publish(self, png, metadata):
        digest = pixel_hash(png)
        current = self.current()
        if current and current[0]["digest"] == digest:
            return False
        atomic_write(self.directory / f"{digest}.png", png)
        write_json(self.manifest, {**metadata, "digest": digest})
        # Keep the previous image too; disk usage stays bounded during normal operation.
        keep = {digest, current[0]["digest"] if current else ""}
        for path in self.directory.glob("*.png"):
            if path.stem not in keep:
                path.unlink(missing_ok=True)
        return True


def viewport_for(config, name):
    """The viewer reports real pixel sizes; config is the headless-boot fallback."""
    try:
        sizes = json.loads((Path(config["cache_dir"]) / config["location"] / "screens.json").read_text())
        width, height = sizes[name]
        if all(type(x) is int and 100 <= x <= 7680 for x in (width, height)):
            return {"width": width, "height": height}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    width, height = config["channels"][name]["viewport"]
    return {"width": width, "height": height}
