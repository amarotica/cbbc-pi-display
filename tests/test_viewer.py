"""Qt offscreen checks: no physical display or X server is needed."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtWidgets import QApplication
from PIL import Image

from signage.common import SnapshotStore
from signage.viewer import MenuWindow, matching_screens, reconcile_windows

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

    def test_screen_selection_uses_connector_names_not_enumeration_order(self):
        food, drinks = Mock(), Mock()
        food.name.return_value = "HDMI-A-1"
        drinks.name.return_value = "HDMI-A-2"
        config = {"channels": {"food": {"output": "HDMI-A-1"}, "drinks": {"output": "HDMI-A-2"}}}
        self.assertEqual(matching_screens(config, [drinks, food]), {"food": food, "drinks": drinks})

    def test_unplugged_food_window_is_closed_instead_of_appearing_on_drinks(self):
        screen = Mock()
        screen.name.return_value = "HDMI-A-2"
        screen.geometry().width.return_value = 1920
        screen.geometry().height.return_value = 1080
        screen.devicePixelRatio.return_value = 1
        app = Mock()
        app.screens.return_value = [screen]
        food_window, drinks_window = Mock(), Mock()
        drinks_window.windowHandle().screen.return_value = screen
        windows = {"food": food_window, "drinks": drinks_window}
        config = {"channels": {"food": {"output": "HDMI-A-1"}, "drinks": {"output": "HDMI-A-2"}}}
        with patch("signage.viewer.MenuWindow") as create:
            sizes = reconcile_windows(config, app, windows)
            create.assert_not_called()
        food_window.close.assert_called_once()
        self.assertNotIn("food", windows)
        drinks_window.windowHandle().setScreen.assert_not_called()
        self.assertEqual(sizes, {"drinks": [1920, 1080]})


if __name__ == "__main__":
    unittest.main()
