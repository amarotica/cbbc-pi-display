"""Fullscreen local images; repaint only after a new image has decoded."""
import argparse
import logging
from pathlib import Path
import signal
import subprocess
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget

from signage.common import SnapshotStore, load_config, write_json
from signage.display import configure_outputs, connected_outputs

LOG = logging.getLogger("signage.viewer")


class MenuWindow(QWidget):
    def __init__(self, screen, store, title):
        super().__init__()
        self.store = store
        self.title = title
        self.image = QPixmap()
        self.version = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setCursor(Qt.BlankCursor)
        self.setStyleSheet("background-color:black")
        self.setGeometry(screen.geometry())
        self.show()
        self.windowHandle().setScreen(screen)
        self.showFullScreen()
        self.refresh()

    def refresh(self):
        try:
            stat = self.store.manifest.stat()
            version = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return
        if version == self.version:
            return
        current = self.store.current()
        if current:
            image = QPixmap()
            if image.loadFromData(current[1], "PNG") and not image.isNull():
                self.image = image  # Decoded before replacing the image being painted.
                self.version = version
                self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if not self.image.isNull():
            size = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            x = (self.width() - size.width()) // 2
            y = (self.height() - size.height()) // 2
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(x, y, size.width(), size.height(), self.image)
        else:
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, f"Common Block\n{self.title}\nWaiting for first menu")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/cbbc-signage/config.json")
    parser.add_argument("--list-outputs", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.list_outputs:
        print("\n".join(connected_outputs()))
        return
    config = load_config(args.config)
    topology = configure_outputs(config)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setOverrideCursor(Qt.BlankCursor)
    windows = {}
    last_sizes = None

    def reconcile():
        nonlocal last_sizes
        screens = {screen.name(): screen for screen in app.screens()}
        sizes = {}
        for name, channel in config["channels"].items():
            screen = screens.get(channel["output"])
            window = windows.get(name)
            if screen is None:
                if window:
                    window.close()
                    del windows[name]
                continue
            if window is None:
                LOG.info("%s on %s", name, screen.name())
                window = windows[name] = MenuWindow(
                    screen, SnapshotStore(config["cache_dir"], config["location"], name), name.title())
            if window.windowHandle().screen() != screen:
                window.windowHandle().setScreen(screen)
            if window.geometry() != screen.geometry():
                window.setGeometry(screen.geometry())
                window.showFullScreen()
            window.refresh()
            sizes[name] = [screen.geometry().width(), screen.geometry().height()]
        if sizes != last_sizes:
            write_json(Path(config["cache_dir"]) / config["location"] / "screens.json", sizes)
            last_sizes = sizes

    def check_topology():
        nonlocal topology
        try:
            if tuple(connected_outputs()) != topology:
                topology = configure_outputs(config)
        except (OSError, subprocess.SubprocessError):
            LOG.exception("Could not configure displays; retrying")

    # Keep the GUI event loop responsive to signals and display hotplug events.
    timer = QTimer()
    timer.timeout.connect(reconcile)
    timer.start(1000)
    outputs_timer = QTimer()
    outputs_timer.timeout.connect(check_topology)
    outputs_timer.start(10000)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    reconcile()
    raise SystemExit(app.exec_())


if __name__ == "__main__":
    main()
