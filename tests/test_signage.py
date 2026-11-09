import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image, PngImagePlugin

from signage.common import SnapshotStore, atomic_write, load_config, pixel_hash, viewport_for
from signage.worker import browser_options, update_channel

ROOT = Path(__file__).resolve().parents[1]


def png(color, note=""):
    stream = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("note", note)
    Image.new("RGB", (100, 100), color).save(stream, format="PNG", pnginfo=metadata)
    return stream.getvalue()


class SignageTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output" / "tmp").mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "output" / "tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config_path = self.root / "config.json"
        self.config_path.write_bytes((ROOT / "config.example.json").read_bytes())
        self.config = load_config(self.config_path, "lmt-pi-12")
        self.config["cache_dir"] = str(self.root)
        self.store = SnapshotStore(self.root, "lmt", "food")

    def test_hostname_mapping_for_both_locations(self):
        for location in ("mfr", "lmt"):
            config = load_config(self.config_path, f"{location}-pi-25.local")
            self.assertEqual(config["channels"]["food"]["url"], f"https://commonblockbrewing.com/{location}-food-specials/")
            self.assertEqual(config["channels"]["drinks"]["url"], f"https://commonblockbrewing.com/{location}-drink-specials/")
        with self.assertRaises(ValueError):
            load_config(self.config_path, "raspberrypi")

    def test_location_override(self):
        data = json.loads(self.config_path.read_text())
        data["location"] = "mfr"
        self.config_path.write_text(json.dumps(data))
        self.assertEqual(load_config(self.config_path, "raspberrypi")["location"], "mfr")

    def test_unchanged_pixels_do_not_replace_manifest(self):
        self.assertTrue(self.store.publish(png("red", "first"), {"published_at": "first"}))
        before = self.store.manifest.stat().st_mtime_ns
        self.assertFalse(self.store.publish(png("red", "second"), {"published_at": "second"}))
        self.assertEqual(self.store.manifest.stat().st_mtime_ns, before)
        self.assertEqual(self.store.current()[0]["published_at"], "first")

    def test_changes_persist_across_restart_and_keep_bounded_history(self):
        for color in ("red", "blue", "green", "yellow"):
            self.store.publish(png(color), {})
        restarted = SnapshotStore(self.root, "lmt", "food")
        self.assertEqual(pixel_hash(restarted.current()[1]), pixel_hash(png("yellow")))
        self.assertEqual(len(list(self.store.directory.glob("*.png"))), 2)
        self.assertIsNone(SnapshotStore(self.root, "mfr", "food").current())

    def test_failed_atomic_replace_preserves_old_content(self):
        path = self.root / "atomic"
        atomic_write(path, b"old")
        with patch("signage.common.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                atomic_write(path, b"new")
        self.assertEqual(path.read_bytes(), b"old")
        self.assertFalse(list(self.root.glob(".pending-*")))

    def test_corrupt_candidate_cannot_replace_valid_snapshot(self):
        self.store.publish(png("blue"), {})
        with self.assertRaises(OSError):
            self.store.publish(b"invalid PNG", {})
        self.assertEqual(pixel_hash(self.store.current()[1]), pixel_hash(png("blue")))

    def test_tampered_cache_is_not_returned(self):
        self.store.publish(png("red"), {})
        digest = self.store.current()[0]["digest"]
        (self.store.directory / f"{digest}.png").write_bytes(png("blue"))
        self.assertIsNone(self.store.current())

    def test_monitor_report_cannot_override_the_websites_fixed_viewport(self):
        report = self.root / "lmt" / "screens.json"
        report.parent.mkdir()
        report.write_text(json.dumps({"food": [2160, 3840]}))
        self.assertEqual(viewport_for(self.config, "food"), {"width": 1080, "height": 1920})
        report.write_text('{"food": [0, "bad"]}')
        self.assertEqual(viewport_for(self.config, "food"), {"width": 1080, "height": 1920})

    def test_legacy_output_names_are_normalized_and_alias_collisions_rejected(self):
        data = json.loads(self.config_path.read_text())
        data["channels"]["food"]["output"] = "HDMI-1"
        self.config_path.write_text(json.dumps(data))
        self.assertEqual(load_config(self.config_path, "mfr-pi-1")["channels"]["food"]["output"], "HDMI-A-1")
        data["channels"]["drinks"]["output"] = "HDMI-A-1"
        self.config_path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_config(self.config_path, "mfr-pi-1")

    def test_worker_uses_system_chromium_with_sandbox(self):
        with patch("signage.worker.shutil.which", return_value="/usr/bin/chromium"):
            self.assertEqual(browser_options(self.config), {"headless": True, "chromium_sandbox": True,
                                                          "executable_path": "/usr/bin/chromium"})
        with patch("signage.worker.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                browser_options(self.config)

    def test_outage_keeps_cached_menu_and_other_channel_can_update(self):
        self.store.publish(png("red"), {})
        before = self.store.manifest.read_bytes()
        with patch("signage.worker.render", new=AsyncMock(side_effect=TimeoutError("offline"))):
            self.assertFalse(asyncio.run(update_channel(None, self.config, "food")))
        self.assertEqual(self.store.manifest.read_bytes(), before)
        with patch("signage.worker.render", new=AsyncMock(return_value=png("green"))):
            self.assertTrue(asyncio.run(update_channel(None, self.config, "drinks")))
        self.assertIsNotNone(SnapshotStore(self.root, "lmt", "drinks").current())


if __name__ == "__main__":
    (ROOT / "output" / "tmp").mkdir(parents=True, exist_ok=True)
    unittest.main()
