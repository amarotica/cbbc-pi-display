"""Qt offscreen checks: no physical display or X server is needed."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtWidgets import QApplication
from PIL import Image

from signage.common import SnapshotStore
from signage.viewer import MenuWindow

ROOT = Path(__file__).resolve().parents[1]


def png(color):
    stream = io.BytesIO()
    Image.new("RGB", (100, 100), color).save(stream, "PNG")
    return stream.getvalue()


class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        (ROOT / "output" / "tmp").mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "output" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.store = SnapshotStore(temporary.name, "lmt", "food")
        self.store.publish(png("red"), {})
        self.window = MenuWindow(self.app.primaryScreen(), self.store, "Food")
        self.addCleanup(self.window.close)

    def test_unchanged_snapshot_does_not_request_repaint(self):
        with patch.object(self.window, "update") as update:
            self.window.refresh()
            update.assert_not_called()

    def test_corrupt_replacement_preserves_displayed_pixels(self):
        before = self.window.image.toImage()
        self.store.manifest.write_text("invalid manifest")
        self.window.refresh()
        self.assertEqual(self.window.image.toImage(), before)

    def test_new_snapshot_replaces_only_after_loading(self):
        before = self.window.image.toImage()
        self.store.publish(png("blue"), {})
        self.window.refresh()
        self.assertNotEqual(self.window.image.toImage(), before)
        restarted = MenuWindow(self.app.primaryScreen(), self.store, "Food")
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.image.toImage(), self.window.image.toImage())


if __name__ == "__main__":
    unittest.main()
