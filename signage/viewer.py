"""Fullscreen local images; repaint only after a new image has decoded."""
import argparse
import logging
import signal
import subprocess
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget

from signage.common import SnapshotStore, load_config
from signage.display import configure_outputs

LOG = logging.getLogger("signage.viewer")


class MenuWindow(QWidget):
    def __init__(self, screen, store, title):
        super().__init__()
        self.store = store
        self.title = title
        self.image = QPixmap()
        self.version = None
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setCursor(Qt.BlankCursor)
        self.setStyleSheet("background-color:black")
        # Allocate without mapping on the default monitor. QtWayland uses this
        # QScreen's wl_output in its xdg_toplevel.set_fullscreen request.
        self.winId()
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


def matching_screens(config, screens):
    """An absent connector must never fall back to another screen."""
    by_name = {screen.name(): screen for screen in screens}
    return {name: by_name.get(channel["output"]) for name, channel in config["channels"].items()}


def reconcile_windows(config, app, windows):
    sizes = {}
    for name, screen in matching_screens(config, app.screens()).items():
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
        elif window.windowHandle().screen() != screen:
            # A disconnect can make Qt move a window to the remaining display.
            window.hide()
            window.windowHandle().setScreen(screen)
            window.showFullScreen()
        window.refresh()
        sizes[name] = [round(screen.geometry().width() * screen.devicePixelRatio()),
                       round(screen.geometry().height() * screen.devicePixelRatio())]
    return sizes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/cbbc-signage/config.json")
    parser.add_argument("--list-outputs", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv[:1])
    if args.list_outputs:
        print("\n".join(screen.name() for screen in app.screens()))
        return
    config = load_config(args.config)
    if app.platformName() != "wayland":
        raise SystemExit("Start the viewer inside the labwc session with QT_QPA_PLATFORM=wayland")
    configure_outputs(config)
    app.setQuitOnLastWindowClosed(False)
    app.setOverrideCursor(Qt.BlankCursor)
    windows = {}

    def reconcile():
        reconcile_windows(config, app, windows)

    def check_topology():
        try:
            configure_outputs(config)
        except (OSError, ValueError, subprocess.SubprocessError):
            LOG.exception("Could not configure displays; retrying")

    # Keep the GUI event loop responsive to signals and display hotplug events.
    timer = QTimer()
    timer.timeout.connect(reconcile)
    timer.start(1000)
    outputs_timer = QTimer()
    outputs_timer.timeout.connect(check_topology)
    outputs_timer.start(10000)
    app.screenRemoved.connect(lambda *_: reconcile())
    app.screenAdded.connect(lambda *_: reconcile())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    reconcile()
    raise SystemExit(app.exec_())


if __name__ == "__main__":
    main()
