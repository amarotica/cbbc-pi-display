"""Native wlroots output layout for the existing labwc desktop."""
import re
import subprocess

TRANSFORMS = {"normal": "normal", "left": "90", "inverted": "180", "right": "270"}


def output_name(name):
    """Accept the previous installer's X11 HDMI names during upgrades."""
    return re.sub(r"^HDMI-(\d+)$", r"HDMI-A-\1", name)


def parse_outputs(text):
    """Parse wlr-randr's text format (also supported by Trixie's 0.4.x)."""
    outputs = []
    current = None
    for line in text.splitlines():
        if line and not line[0].isspace():
            current = {"name": line.split()[0], "modes": []}
            outputs.append(current)
        elif current is not None:
            line = line.strip()
            mode = re.fullmatch(r"(\d+)x(\d+) px(?:, ([\d.]+) Hz)?(?: \(([^)]*)\))?", line)
            if mode:
                width, height, refresh, flags = mode.groups()
                current["modes"].append({"width": int(width), "height": int(height),
                                         "refresh": refresh, "flags": flags or ""})
            elif line.startswith("Enabled: "):
                current["enabled"] = line.removeprefix("Enabled: ") == "yes"
            elif line.startswith("Position: "):
                current["position"] = tuple(int(x) for x in line.removeprefix("Position: ").split(","))
            elif line.startswith("Transform: "):
                current["transform"] = line.removeprefix("Transform: ")
            elif line.startswith("Scale: "):
                current["scale"] = float(line.removeprefix("Scale: "))
    return outputs


def read_outputs():
    result = subprocess.run(["wlr-randr"], check=True, capture_output=True, text=True, timeout=10)
    return parse_outputs(result.stdout)


def configure_outputs(config):
    """Apply one atomic layout transaction, only when settings actually differ."""
    outputs = read_outputs()
    by_name = {output["name"]: output for output in outputs}
    command = ["wlr-randr"]
    changed = False
    x = 0
    for name in ("food", "drinks"):
        channel = config["channels"][name]
        output = by_name.get(output_name(channel["output"]))
        if output is None:
            continue
        modes = output["modes"]
        mode = next((m for m in modes if "current" in m["flags"]), None)
        mode = mode or next((m for m in modes if "preferred" in m["flags"]), None)
        mode = mode or (modes[0] if modes else None)
        if mode is None:
            raise ValueError(f"No usable mode advertised by {output['name']}")
        transform = TRANSFORMS[channel.get("rotation", "normal")]
        changed |= (not output.get("enabled") or output.get("position") != (x, 0)
                    or output.get("transform") != transform or output.get("scale") != 1)
        mode_name = f"{mode['width']}x{mode['height']}"
        if mode["refresh"]:
            mode_name += f"@{mode['refresh']}Hz"
        command += ["--output", output["name"], "--on", "--mode", mode_name,
                    "--transform", transform, "--scale", "1", "--pos", f"{x},0"]
        x += mode["height"] if transform in {"90", "270"} else mode["width"]
    if changed:
        subprocess.run(command, check=True, timeout=10)
    return tuple(output["name"] for output in outputs)
