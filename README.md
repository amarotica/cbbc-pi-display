# Common Block Raspberry Pi signage

Dual-display, unattended signage for Raspberry Pi 4. Both displays default to portrait orientation, rotated 90 degrees counterclockwise. The hostname selects the venue; no per-Pi URL editing is needed.

| Hostname | Food: HDMI-A-1 | Drinks: HDMI-A-2 |
| --- | --- | --- |
| `lmt-pi-N` | `https://commonblockbrewing.com/lmt-food-specials/` | `https://commonblockbrewing.com/lmt-drink-specials/` |
| `mfr-pi-N` | `https://commonblockbrewing.com/mfr-food-specials/` | `https://commonblockbrewing.com/mfr-drink-specials/` |

`N` can be any nonnegative integer. There is no fixed limit on the number of Pis. Each Pi fetches its own two menus independently.

## Install on each Pi

Use an existing **Raspberry Pi OS Desktop 64-bit installation with LightDM and labwc/Wayland**, such as the Trixie desktop running on your Pis. The installer reuses that desktop and enables automatic login for the selected existing account. It requires an installed labwc Wayland session and fails before installing packages if it cannot find one. Lite, X11-only desktops, and Wayfire sessions are outside this installer's scope.

Set up networking, SSH, and a hostname such as `lmt-pi-1` or `mfr-pi-2` beforehand. No desktop replacement or display-manager switch is performed.

Connect both displays. Copy this repository to the Pi, SSH in as your normal user, and from the repository directory run:

```bash
sudo bash setup.sh
sudo reboot
```

If installing from a root shell, specify the existing kiosk account:

```bash
sudo bash setup.sh --user YOUR_USERNAME
```

The installer adds Python/venv, PyQt5, Pillow, Qt's Wayland plugin (`qtwayland5`), and the small `wlr-randr` output utility. It reuses `chromium` or `chromium-browser` already installed on the desktop; if neither is present, it installs the distribution's `chromium` package. Playwright is installed as a Python dependency, but **no Playwright browser download or `install --with-deps` bundle is run**. It does not install Xorg, Openbox, or another LightDM instance.

Installation needs internet access for missing packages and Python dependencies. It does not reboot automatically. Repeat installation from an updated checkout to update the software; custom menu settings and cached PNGs are preserved. Setup applies `left` (90 degrees counterclockwise) rotation to both channels, including existing installs, and orients the configured viewports to portrait. To install a different orientation, use `sudo bash setup.sh --rotation normal` (or `right` / `inverted`). Updates take effect fully after a reboot.

The existing user labwc autostart file receives one managed launch block. Unrelated startup commands are preserved; changed existing files receive a `.before-cbbc-signage` backup. With Pi's `labwc -m`, the system autostart continues running separately. The setup disables standard `swayidle` blanking for the signage account, and uses the Pi's screen-blanking setting when available. The launcher stops the account's existing `swayidle` process at startup. Custom screen-locking/power-management programs need separate configuration.

**Upgrading from the earlier X11 installer:** run the same setup command. It migrates `HDMI-1`/`HDMI-2` config entries to `HDMI-A-1`/`HDMI-A-2`, replaces the old LightDM kiosk override with the installed labwc session, and retires the old `cbbc-signage.desktop` X11 session entry. Other config values and caches are kept. Old graphics packages and previously downloaded browser files are left installed; this upgrade does not attempt package removal.

After reboot, LightDM logs into the existing labwc desktop automatically. Its autostart starts the native Wayland viewer, which requests fullscreen on each named output before mapping the window. The launcher prevents duplicate viewer instances and restarts the viewer after a crash while the graphical session is alive. No keyboard, mouse, browser prompts, or website login are involved. The background updater starts at boot without waiting for internet access. A display without a successful cached fetch shows “Waiting for first menu”; the other display continues independently.

## How updates and outages work

1. Every five minutes, a fresh hidden Chromium process loads each page in a fresh browser context. HTTP caches and service workers cannot reuse stale browser content. The two pages render sequentially to limit Pi memory usage.
2. The renderer checks the HTTP response, expected URL, readiness selector, image decoding, CSS background images, and fonts. It rejects missing assets, empty content, unexpected redirects, and pages that are still changing between two captures.
3. It captures exactly the **visible browser viewport**, 1080 × 1920 pixels by default at device scale factor 1. It does not capture a long document and shrink it to the TV. Pixel hashes ignore PNG metadata. Unchanged pixels cause no cache replacement or viewer update.
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
| `browser_executable` | `null` finds system `chromium`/`chromium-browser`; an explicit executable path overrides discovery. |
| Channel `output` | Exact Wayland connector name; default food `HDMI-A-1`, drinks `HDMI-A-2`. Previous `HDMI-1`/`HDMI-2` names are also accepted as aliases. |
| Channel `viewport` | Fixed browser CSS width/height, default `[1080, 1920]`. Monitor reports never override this. |
| Channel `rotation` | `left` (default, 90 degrees counterclockwise), `right` (clockwise), `normal`, or `inverted`; controls the physical output orientation. |
| Channel `url` | Optional per-channel URL override. |
| Channel `ready_selector` | A visible menu element required before capture. |
| Channel `capture_selector` | Region to validate for media readiness and required text; `null` validates the body. Capture always remains the fixed viewport. |
| Channel `required_text` | Optional exact text that must appear in the capture region. |

Each website gets a stable **1080 × 1920 CSS-pixel content box** by default. The screenshot is the same 1080 × 1920 pixel size, with browser device scale factor 1 and no browser toolbar or scrollbar. A portrait Full HD output therefore displays it at 1:1 size. If an output has a different resolution, the viewer scales the snapshot uniformly, preserving aspect ratio.

The page canvas (`html` and `body`) and the viewer's surrounding fill use the menu blue, `#0b3c4a`, so unused space below the content blends into the menu background. Backgrounds on individual page elements remain under the website's control.

The **website owns all layout**: use the full viewport for its background and fit the header plus media within it. For example, `html, body { margin: 0; width: 100%; height: 100%; }` and a `100dvh` menu layout provide the available box. Match header/media widths and use aspect-preserving CSS such as `object-fit: contain` on the website. Content below or outside the visible viewport is clipped, as it would be in a fullscreen browser; the Pi does not scroll or resize the document to include it. Existing `screens.json` files from earlier versions are ignored.

Displays should be powered on at boot; if a TV does not advertise a connector while off, that menu window appears when it reconnects. A missing channel's window is closed immediately on Qt's screen-removal notification so it does not remain on the other TV.

The signage viewer controls the two configured outputs' layout using `wlr-randr`: food at the left, drinks at the right, scale 1, with the requested rotations. It checks every ten seconds and only applies an output transaction when settings differ, avoiding repeated display mode resets on an unchanged desktop. Any additional outputs are left alone. Avoid configuring a competing automatic output profile with a different layout for these two displays.

**Verify HDMI mapping on the actual Pi.** The Pi 4’s physical ports are labelled HDMI0 and HDMI1; labwc commonly names the outputs `HDMI-A-1` and `HDMI-A-2`. Connector names and cabling must be checked once on your hardware. It never assigns food/drinks by monitor enumeration order or moves a missing channel onto the other screen.

To inspect connector names from SSH while the kiosk is running:

```bash
# SSH as the same account selected during setup (support on your current Pi).
XDG_RUNTIME_DIR="/run/user/$(id -u)" WAYLAND_DISPLAY=wayland-0 wlr-randr
```

If the session's socket is not named `wayland-0`, find it with `find "/run/user/$(id -u)" -maxdepth 1 -type s -name 'wayland-*'` and use that socket's filename as `WAYLAND_DISPLAY`. These commands inspect the running desktop over SSH; `$XDG_SESSION_TYPE` in the SSH shell itself describes the SSH login, not the graphical session.

If your system uses different connector names, update the channel `output` values. `left` applies Wayland's `90` transform (counterclockwise); `right` applies `270` (clockwise). TVs that boot with missing EDID may require fixed video modes in Raspberry Pi OS; this installer leaves boot firmware settings unchanged.

To rotate an existing installation counterclockwise without rerunning package installation, first copy this updated checkout to the Pi, then run from its repository directory:

```bash
sudo python3 -m signage.desktop_setup \
    --migrate-config /etc/cbbc-signage/config.json --rotation left
sudo reboot
```

This updates both rotations and configured viewport orientations using a JSON parser, preserving temporary URL overrides and other menu settings. It saves a backup when no `.before-cbbc-signage` backup already exists. The viewer reads rotation at startup, so restarting only the updater does not apply it. Cached menus remain visible offline; fresh renders use the configured fixed viewport.

## Website readiness and current source-page findings

The default selectors match the currently live Divi page:

```json
"ready_selector": "#main-content .et_pb_image img",
"capture_selector": "#main-content"
```

Create the other three pages using the same structure, or adjust each channel’s selectors. A generic HTTP-200 maintenance/error page can only be recognized reliably with a website-specific contract. For stronger validation, add a unique attribute to the actual menu container, such as `data-signage="lmt-food"`, use `[data-signage="lmt-food"]` as its readiness/validation selector, and set `required_text` to a permanent heading that must be present. If content is populated asynchronously, expose the readiness marker only when that content is complete. Apply corresponding markers to the other venue/menu pages. The default image selector already rejects ordinary WordPress error pages that lack the menu structure.

Inspection on November 9, 2026 found that `/lmt-food-specials/` currently has a **DRINK SPECIALS** heading and an image named `LMT-Drink-and-Food-Specials-No-Header-scaled.png`. The configured food URL is preserved as requested; review the page content before rollout. The source site's Divi column widths, header sizing, and media fitting need to be designed for the fixed portrait viewport on the website itself.

## Operation and troubleshooting

```bash
# Updater activity and failures (includes the reason a candidate was rejected).
sudo journalctl -u cbbc-signage-updater -f

# Graphical login and viewer startup issues.
sudo journalctl -u lightdm -b
sudo journalctl -t cbbc-signage-viewer -b

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
.venv/bin/python -m signage.worker --once
sudo systemctl start cbbc-signage-updater
```

`--once` exits nonzero if either menu fails. Until all four source URLs are live, a Pi can legitimately keep one or both channels in the waiting state. An outage never replaces an existing menu with that waiting message. Keep normal OS security updates enabled/maintained; the installer does not configure automatic OS upgrades. Chromium runs as the chosen non-root account with its sandbox enabled. Playwright drives the distribution's Chromium executable; verify a fetch on the Pi after significant browser or Playwright updates.

To stop signage and disable automatic kiosk login:

```bash
sudo systemctl disable --now cbbc-signage-updater
sudo rm /etc/lightdm/lightdm.conf.d/99-cbbc-signage.conf
```

Restore `~/.config/labwc/autostart.before-cbbc-signage` if that backup exists, or remove the block between `# BEGIN CBBC SIGNAGE` and `# END CBBC SIGNAGE` from the current autostart file. Re-enable screen blanking through your desktop settings if desired, then reboot. The existing desktop remains available. Cached menus remain under `/var/lib/cbbc-signage`. Other pre-existing LightDM settings can still enable autologin after removing this project's override.

## Validation

Core checks (Python plus Pillow):

```bash
python -m unittest discover -s tests -p test_signage.py -v
```

Desktop setup/output-layout checks:

```bash
python -m unittest discover -s tests -p test_desktop.py -v
```

Real Chromium integration checks for development (install `requirements.txt` and run `python -m playwright install --only-shell chromium` first; this test-only download is not used by the Pi installer):

```bash
python -m unittest discover -s tests -p test_renderer.py -v
```

On the Pi, test the actual desktop browser without downloading a test browser:

```bash
SIGNAGE_TEST_BROWSER="$(command -v chromium || command -v chromium-browser)" \
    /opt/cbbc-signage/.venv/bin/python -m unittest discover -s tests -p test_renderer.py -v
```

Run that command from the source checkout, where `tests/` exists.

The viewer also has offscreen Qt checks (`python -m unittest discover -s tests -p test_viewer.py -v`), using the PyQt5 package installed on the Pi. They verify unchanged images do not request repaints, corrupt candidates retain displayed pixels, and a restarted viewer loads the persisted menu.

The local-server integration tests exercise exact viewport capture (including all four corners of 1080 × 1920), tall/offset content, HTTP failures, redirects, broken images/backgrounds, unstable/empty pages, missing readiness markers, and wrong menu text. Core tests cover fixed viewport isolation from monitor reports, venue routing, output isolation, unchanged pixels, atomic writes, cache integrity, offline restart persistence, and independent channel failures. Desktop tests cover config migration, preserved startup commands, repeat installation, missing/rotated outputs, and avoiding display changes on an already-correct layout. Physical native-Wayland dual-HDMI placement, boot autologin, TV reconnect behavior, and power-loss recovery still require an actual Pi acceptance test.

Before deploying all units: install one Pi, confirm both mappings, publish a changed menu, verify unchanged polling has no visible effect, unplug networking, and reboot offline to confirm both menus persist. Then reconnect networking and confirm updates resume.

Implementation references: [labwc autostart and configuration](https://labwc.github.io/labwc-config.5.html), [QtWayland fullscreen output selection](https://github.com/qt/qtwayland/blob/5.15/src/plugins/shellintegration/xdg-shell/qwaylandxdgshell.cpp), [wlr-randr on Trixie](https://manpages.debian.org/trixie/wlr-randr/wlr-randr.1.en.html), [Raspberry Pi kiosk setup](https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/).
