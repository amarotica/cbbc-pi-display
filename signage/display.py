"""X11 connector discovery and explicit food/drinks output placement."""
import re
import subprocess


def connected_outputs():
    result = subprocess.run(["xrandr", "--query"], check=True, capture_output=True, text=True, timeout=10)
    return re.findall(r"^(\S+) connected\b", result.stdout, re.MULTILINE)


def configure_outputs(config):
    connected = connected_outputs()
    previous = None
    for channel in config["channels"].values():
        output = channel["output"]
        if output not in connected:
            continue
        command = ["xrandr", "--output", output, "--auto", "--rotate", channel.get("rotation", "normal")]
        command += ["--right-of", previous] if previous else ["--primary", "--pos", "0x0"]
        subprocess.run(command, check=True, timeout=10)
        previous = output
    return tuple(connected)
