"""Independent updater; the viewer never waits on the network or Chromium."""
import argparse
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import time

from signage.common import SnapshotStore, load_config, viewport_for, write_json
from signage.renderer import render

LOG = logging.getLogger("signage")


async def update_channel(browser, config, name):
    store = SnapshotStore(config["cache_dir"], config["location"], name)
    status_path = store.directory / "status.json"
    now = datetime.now(timezone.utc).isoformat()
    try:
        png = await render(browser, config["channels"][name], config, viewport_for(config, name))
        changed = store.publish(png, {"url": config["channels"][name]["url"], "published_at": now})
        write_json(status_path, {"checked_at": now, "ok": True, "changed": changed})
        LOG.info("%s: %s", name, "published new menu" if changed else "unchanged")
        return True
    except Exception as error:
        LOG.warning("%s: retaining last menu: %s", name, error)
        write_json(status_path, {"checked_at": now, "ok": False, "error": str(error)})
        return False


async def run(config, once=False):
    from playwright.async_api import async_playwright

    while True:
        started = time.monotonic()
        results = []
        async with async_playwright() as playwright:
            # Start a fresh process each cycle to bound long-term browser resource usage.
            browser = await playwright.chromium.launch(headless=True, chromium_sandbox=True)
            try:
                # Sequential rendering limits memory pressure on the Pi 4.
                for name in config["channels"]:
                    results.append(await update_channel(browser, config, name))
            finally:
                await browser.close()
        if once:
            return 0 if all(results) else 1
        await asyncio.sleep(max(1, config["poll_seconds"] - (time.monotonic() - started)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/cbbc-signage/config.json")
    parser.add_argument("--once", action="store_true", help="Fetch both menus once; exit nonzero on any failure")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    Path(config["cache_dir"]).mkdir(parents=True, exist_ok=True)
    raise SystemExit(asyncio.run(run(config, args.once)))


if __name__ == "__main__":
    main()
