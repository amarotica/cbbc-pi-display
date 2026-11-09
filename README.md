# Common Block Raspberry Pi signage

Dual-display, unattended signage for Raspberry Pi 4. The hostname selects the venue; no per-Pi URL editing is needed.

| Hostname | Food: HDMI-1 | Drinks: HDMI-2 |
| --- | --- | --- |
| `lmt-pi-N` | `https://commonblockbrewing.com/lmt-food-specials/` | `https://commonblockbrewing.com/lmt-drink-specials/` |
| `mfr-pi-N` | `https://commonblockbrewing.com/mfr-food-specials/` | `https://commonblockbrewing.com/mfr-drink-specials/` |

`N` can be any nonnegative integer. There is no fixed limit on the number of Pis. Each Pi fetches its own two menus independently.

## Install on each Pi

Use **Raspberry Pi OS Lite 64-bit, Bookworm or Trixie**, on a dedicated signage Pi. A desktop installation can also be used, but this installer selects its own **X11/LightDM kiosk session**, replacing normal desktop login. It installs packages, enables passwordless graphical login for your existing account, and selects graphical boot. It does not configure Wi-Fi, SSH, or credentials. Set those in Raspberry Pi Imager first, including a hostname such as `lmt-pi-1` or `mfr-pi-2`.

Connect both displays. Copy this repository to the Pi, SSH in as your normal user, and from the repository directory run:

```bash
sudo bash setup.sh
sudo reboot
```

If installing from a root shell, specify the existing kiosk account:

```bash
sudo bash setup.sh --user YOUR_USERNAME
```

The installer downloads a pinned Playwright release and its matching Chromium browser, including ARM64 dependencies. Installation needs internet access and enough free SD-card space for the browser and packages. It does not reboot automatically. Repeat installation from an updated checkout to update the software; existing `/etc/cbbc-signage/config.json` and cached menus are preserved. Updates take effect fully after a reboot.

After reboot, LightDM logs in automatically and starts the two fullscreen menu windows. No keyboard, mouse, browser prompts, or website login are involved. The background updater starts at boot without waiting for internet access. A display without a successful cached fetch shows “Waiting for first menu”; the other display continues independently.

## How updates and outages work

1. Every five minutes, a fresh hidden Chromium process loads each page in a fresh browser context. HTTP caches and service workers cannot reuse stale browser content. The two pages render sequentially to limit Pi memory usage.
2. The renderer checks the HTTP response, expected URL, readiness selector, image decoding, CSS background images, and fonts. It rejects missing assets, empty content, unexpected redirects, and pages that are still changing between two captures.
3. It captures the **entire selected menu element**, including content below the viewport. Pixel hashes ignore PNG metadata. Unchanged pixels cause no cache replacement or viewer update.
4. A changed image is flushed to disk before the current manifest is replaced atomically. The viewer decodes it before swapping its in-memory image during painting. There is no foreground web-page reload or blank loading screen.
5. Timeouts, DNS failures, HTTP errors (including the three unpublished URLs), failed assets, or Chromium crashes leave the current menu in place. The worker retries automatically. Cached PNGs survive reboots; the viewer does not need the original HTML, fonts, or network to show them.

The normal fetch interval is 300 seconds. Publication takes an additional few seconds for loading, settling, and stability checks. Only current and previous PNGs are retained per menu; status files are overwritten. Network requests still occur on each poll even when nothing changes. The website or CDN must serve fresh content; client-side checks cannot bypass an incorrectly configured upstream cache. SD-card corruption or hardware failure can still destroy a cache.

**Static content only:** displays show rendered snapshots, so videos, scrolling, interactions, clocks, and animations do not play. Iframes/videos inside the capture region are rejected. For text/image menus, snapshots make offline operation and steady output straightforward.

## Configure menus and displays

Edit `/etc/cbbc-signage/config.json`, then reboot (or restart the updater and the graphical session). The example in this repository contains all defaults.

| Setting | Meaning |
| --- | --- |
| `location` | `null` infers `lmt` or `mfr` from the hostname. Set it explicitly to override. Cached content is separated by venue and menu. |
| `poll_seconds` | Seconds between fetch cycles; default `300`. |
| `timeout_seconds` | Maximum render time per page; default `45`. |
| `settle_seconds` | Wait after page load before capturing; increase for slow JavaScript pages. |
| `stable_seconds` | Interval between two captures which must have identical pixels. |
| `timezone` | Browser timezone; default `America/Los_Angeles`. |
| Channel `output` | Exact X11 connector name; default food `HDMI-1`, drinks `HDMI-2`. |
| Channel `viewport` | Fallback browser width/height before the viewer reports actual screen dimensions. |
| Channel `rotation` | `normal`, `left`, `right`, or `inverted`; controls the physical output orientation. |
| Channel `url` | Optional per-channel URL override. |
| Channel `ready_selector` | A visible menu element required before capture. |
| Channel `capture_selector` | Element to capture in full; `null` captures the full document. |
| Channel `required_text` | Optional exact text that must appear in the capture region. |

The viewer reports the actual dimensions of each screen to the updater, including rotation. The whole captured image fits the screen with its aspect ratio preserved and black bars where necessary. It does not stretch or crop content. For best legibility, design each source page for the TV’s orientation and aspect ratio. Full-page fitting can make a very tall page small on a landscape TV. Displays should be powered on at boot; if a TV does not advertise a connector while off, that menu window appears when it reconnects (the output layout is checked every ten seconds).

**Verify HDMI mapping on the actual Pi.** The Pi 4’s physical ports are labelled HDMI0 and HDMI1; X11 commonly names them HDMI-1 and HDMI-2. This project interprets your first display as HDMI-1 and your second as HDMI-2. Connector names and cabling must be checked once on your hardware. The installer extends the outputs rather than mirroring them. It never assigns food/drinks by monitor enumeration order or moves a missing channel onto the other screen.

To inspect connector names from SSH while the kiosk is running:

```bash
# Use the same account selected during setup.
DISPLAY=:0 XAUTHORITY="$HOME/.Xauthority" xrandr --query
```

If your system uses different connector names, update the channel `output` values. For a portrait screen, set its `rotation` to `left` or `right`. TVs that boot with missing EDID may require fixed video modes in Raspberry Pi OS; this installer leaves boot firmware settings unchanged.

## Website readiness and current source-page findings

The default selectors match the currently live Divi page:

```json
"ready_selector": "#main-content .et_pb_image img",
"capture_selector": "#main-content"
```

Create the other three pages using the same structure, or adjust each channel’s selectors. A generic HTTP-200 maintenance/error page can only be recognized reliably with a website-specific contract. For stronger validation, add a unique attribute to the actual menu container, such as `data-signage="lmt-food"`, use `[data-signage="lmt-food"]` as its readiness/capture selector, and set `required_text` to a permanent heading that must be present. If content is populated asynchronously, expose the readiness marker only when that content is complete. Apply corresponding markers to the other venue/menu pages. The default image selector already rejects ordinary WordPress error pages that lack the menu structure.

Inspection on November 9, 2026 found that `/lmt-food-specials/` currently has a **DRINK SPECIALS** heading and an image named `LMT-Drink-and-Food-Specials-No-Header-scaled.png`. The configured food URL is preserved as requested; review the page content before rollout. Its menu is taller than a normal landscape viewport, which is why the default captures the whole menu instead of only the top of the page.

## Operation and troubleshooting

```bash
# Updater activity and failures (includes the reason a candidate was rejected).
sudo journalctl -u cbbc-signage-updater -f

# Graphical login and viewer startup issues.
sudo journalctl -u lightdm -b
tail -n 100 "$HOME/.xsession-errors"

# Last attempt and last successfully published image metadata.
cat /var/lib/cbbc-signage/lmt/food/status.json
cat /var/lib/cbbc-signage/lmt/food/current.json

# Restart fetching after changing configuration.
sudo systemctl restart cbbc-signage-updater

# Restart the viewer/session too (briefly blanks both TVs).
sudo systemctl restart lightdm
```

For a manual fetch, stop the worker first to avoid simultaneous writers, run as the configured kiosk user, then start the service again:

```bash
sudo systemctl stop cbbc-signage-updater
cd /opt/cbbc-signage
PLAYWRIGHT_BROWSERS_PATH=/opt/cbbc-signage/browsers .venv/bin/python -m signage.worker --once
sudo systemctl start cbbc-signage-updater
```

`--once` exits nonzero if either menu fails. Until all four source URLs are live, a Pi can legitimately keep one or both channels in the waiting state. An outage never replaces an existing menu with that waiting message. Keep normal OS security updates enabled/maintained; the installer does not configure automatic OS upgrades. Chromium runs as the chosen non-root account with its sandbox enabled.

To stop signage and disable automatic kiosk login:

```bash
sudo systemctl disable --now cbbc-signage-updater
sudo rm /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf
# Return to console login on a Lite installation:
sudo systemctl set-default multi-user.target
sudo reboot
```

On a previous desktop installation, select its desktop session/display manager again instead of selecting console boot. Cached menus remain under `/var/lib/cbbc-signage`.

## Validation

Core checks (Python plus Pillow):

```bash
python -m unittest discover -s tests -p test_signage.py -v
```

Real Chromium integration checks (install `requirements.txt` and run `python -m playwright install chromium` first):

```bash
python -m unittest discover -s tests -p test_renderer.py -v
```

The viewer also has offscreen Qt checks (`python -m unittest discover -s tests -p test_viewer.py -v`), using the PyQt5 package installed on the Pi. They verify unchanged images do not request repaints, corrupt candidates retain displayed pixels, and a restarted viewer loads the persisted menu.

The local-server integration tests exercise full-height capture, HTTP failures, redirects, broken images/backgrounds, unstable/empty pages, missing readiness markers, and wrong menu text. Core tests cover venue routing, output isolation, unchanged pixels, atomic writes, cache integrity, offline restart persistence, and independent channel failures. Physical dual-HDMI placement, boot autologin, TV reconnect behavior, and power-loss recovery still require an actual Pi acceptance test.

Before deploying all units: install one Pi, confirm both mappings, publish a changed menu, verify unchanged polling has no visible effect, unplug networking, and reboot offline to confirm both menus persist. Then reconnect networking and confirm updates resume.

Implementation references: [Playwright browser installation](https://playwright.dev/python/docs/browsers), [Raspberry Pi kiosk setup](https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/), [Raspberry Pi display configuration](https://www.raspberrypi.com/documentation/computers/configuration.html).
