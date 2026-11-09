import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from signage.desktop_setup import BEGIN, find_session, install_autostart, migrate_config
from signage.display import configure_outputs, parse_outputs

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = '''HDMI-A-1 "First TV (HDMI-A-1)"
  Enabled: yes
  Modes:
    1920x1080 px, 60.000000 Hz (preferred, current)
    1280x720 px, 60.000000 Hz
  Position: 0,0
  Transform: normal
  Scale: 1.000000
HDMI-A-2 "Second TV (HDMI-A-2)"
  Enabled: yes
  Modes:
    1920x1080 px, 60.000000 Hz (preferred, current)
  Position: 1920,0
  Transform: normal
  Scale: 1.000000
'''


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config.example.json").read_text())
        # Tests below start from unrotated physical outputs unless stated otherwise.
        for channel in self.config["channels"].values():
            channel["rotation"] = "normal"
        self.outputs = parse_outputs(OUTPUTS)

    def test_correct_existing_layout_never_applies_a_display_change(self):
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(self.config)
            run.assert_not_called()

    def test_mirrored_outputs_are_extended_in_one_transaction(self):
        self.outputs[1]["position"] = (0, 0)
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(self.config)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command.count("--output"), 2)
        self.assertIn("HDMI-A-1", command)
        self.assertIn("HDMI-A-2", command)
        self.assertIn("1920,0", command)

    def test_portrait_rotation_uses_transformed_width(self):
        self.config["channels"]["food"]["rotation"] = "left"
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(self.config)
        command = run.call_args.args[0]
        self.assertIn("90", command)
        self.assertIn("1080,0", command)

    def test_portrait_defaults_rotate_both_outputs_counterclockwise(self):
        config = json.loads((ROOT / "config.example.json").read_text())
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(config)
        command = run.call_args.args[0]
        self.assertEqual([command[i + 1] for i, arg in enumerate(command) if arg == "--transform"], ["90", "90"])
        self.assertEqual([command[i + 1] for i, arg in enumerate(command) if arg == "--pos"], ["0,0", "1080,0"])

    def test_already_rotated_portrait_outputs_are_not_reconfigured(self):
        config = json.loads((ROOT / "config.example.json").read_text())
        for output in self.outputs:
            output["transform"] = "90"
        self.outputs[1]["position"] = (1080, 0)
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(config)
            run.assert_not_called()

    def test_missing_food_connector_never_changes_drinks_identity(self):
        with patch("signage.display.read_outputs", return_value=self.outputs[1:]), patch("signage.display.subprocess.run") as run:
            configure_outputs(self.config)
        command = run.call_args.args[0]
        self.assertIn("HDMI-A-2", command)
        self.assertNotIn("HDMI-A-1", command)
        self.assertEqual(command.count("--output"), 1)

    def test_disabled_connector_uses_preferred_mode(self):
        self.outputs[1].update(enabled=False, modes=[{"width": 1920, "height": 1080,
                                                     "refresh": "60.000000", "flags": "preferred"}])
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(self.config)
        self.assertIn("1920x1080@60.000000Hz", run.call_args.args[0])

    def test_bad_mode_does_not_apply_a_partial_layout(self):
        self.outputs[1]["modes"] = []
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            with self.assertRaises(ValueError):
                configure_outputs(self.config)
            run.assert_not_called()

    def test_disabled_connector_without_preferred_flag_uses_advertised_mode(self):
        self.outputs[1].update(enabled=False, modes=[{"width": 1920, "height": 1080,
                                                     "refresh": "60.000000", "flags": ""}])
        with patch("signage.display.read_outputs", return_value=self.outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(self.config)
        run.assert_called_once()

    def test_output_mode_without_refresh_rate_is_supported(self):
        outputs = parse_outputs('HDMI-A-1 "TV"\n  Enabled: no\n  Modes:\n    1920x1080 px (preferred)\n')
        with patch("signage.display.read_outputs", return_value=outputs), patch("signage.display.subprocess.run") as run:
            configure_outputs(self.config)
        self.assertIn("1920x1080", run.call_args.args[0])


class DesktopSetupTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output" / "tmp").mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "output" / "tmp")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.system_autostart = self.home / "system-autostart"
        self.system_autostart.write_text("#!/bin/sh\nstart-desktop-panel &\n")
        self.autostart = self.home / ".config/labwc/autostart"
        self.sessions = self.home / "sessions"
        self.sessions.mkdir()

    def test_existing_startup_is_preserved_backed_up_and_install_is_idempotent(self):
        self.autostart.parent.mkdir(parents=True)
        original = "#!/bin/sh\nmy-custom-app &\nswayidle -w timeout 600 'blank' &\nexit 0\n"
        self.autostart.write_text(original)
        install_autostart(self.home, self.system_autostart, merge_config=True)
        first = self.autostart.read_text()
        install_autostart(self.home, self.system_autostart, merge_config=True)
        self.assertEqual(self.autostart.read_text(), first)
        self.assertEqual(first.count(BEGIN), 1)
        self.assertIn("my-custom-app &", first)
        self.assertIn("# CBBC disabled screen blanking: swayidle", first)
        self.assertLess(first.index(BEGIN), first.index("exit 0"))
        self.assertEqual(self.autostart.with_name("autostart.before-cbbc-signage").read_text(), original)

    def test_pi_merge_mode_does_not_duplicate_system_desktop_startup(self):
        install_autostart(self.home, self.system_autostart, merge_config=True)
        self.assertNotIn("start-desktop-panel", self.autostart.read_text())

    def test_nonmerge_mode_keeps_system_desktop_startup(self):
        install_autostart(self.home, self.system_autostart, merge_config=False)
        self.assertIn("start-desktop-panel", self.autostart.read_text())

    def test_incomplete_managed_block_is_not_overwritten(self):
        self.autostart.parent.mkdir(parents=True)
        original = BEGIN + "\ncustom script"
        self.autostart.write_text(original)
        with self.assertRaises(ValueError):
            install_autostart(self.home, self.system_autostart)
        self.assertEqual(self.autostart.read_text(), original)

    def test_old_config_migration_preserves_custom_settings_and_cache_path(self):
        path = self.home / "config.json"
        config = {"cache_dir": "/var/lib/cbbc-signage", "poll_seconds": 77, "channels": {
            "food": {"output": "HDMI-1", "url": "https://example.org/custom"},
            "drinks": {"output": "DP-2"}}}
        original = json.dumps(config)
        path.write_text(original)
        self.assertTrue(migrate_config(path))
        config["channels"]["food"]["output"] = "HDMI-A-1"
        self.assertEqual(json.loads(path.read_text()), config)
        self.assertFalse(migrate_config(path))
        self.assertEqual(path.with_name("config.json.before-cbbc-signage").read_text(), original)

    def test_existing_labwc_session_is_preferred_over_old_kiosk_session(self):
        (self.sessions / "LXDE-pi-labwc.desktop").write_text("[Desktop Entry]\nExec=/usr/bin/labwc-pi\n")
        (self.sessions / "unrelated.desktop").write_text("[Desktop Entry]\nExec=some-other-desktop\n")
        (self.home / ".dmrc").write_text("[Desktop]\nSession=cbbc-signage\n")
        self.assertEqual(find_session(self.home, self.sessions), "LXDE-pi-labwc")

    def test_rotation_upgrade_preserves_urls_and_other_settings(self):
        path = self.home / "config.json"
        config = {"poll_seconds": 77, "channels": {
            "food": {"output": "HDMI-A-1", "rotation": "normal", "viewport": [1920, 1080],
                     "url": "https://example.org/test-food", "ready_selector": "body"},
            "drinks": {"output": "HDMI-A-2", "rotation": "normal", "viewport": [2560, 1440],
                       "url": "https://example.org/test-drinks", "capture_selector": "body"}}}
        path.write_text(json.dumps(config))
        self.assertTrue(migrate_config(path, rotation="left"))
        config["channels"]["food"].update(rotation="left", viewport=[1080, 1920])
        config["channels"]["drinks"].update(rotation="left", viewport=[1440, 2560])
        self.assertEqual(json.loads(path.read_text()), config)
        self.assertFalse(migrate_config(path, rotation="left"))

    def test_rotation_can_return_to_landscape_without_swapping_twice(self):
        path = self.home / "config.json"
        path.write_text(json.dumps({"channels": {"food": {
            "rotation": "left", "viewport": [1080, 1920]}}}))
        self.assertTrue(migrate_config(path, rotation="normal"))
        self.assertEqual(json.loads(path.read_text())["channels"]["food"]["viewport"], [1920, 1080])
        self.assertFalse(migrate_config(path, rotation="normal"))

    def test_missing_desktop_fails_preflight(self):
        with self.assertRaises(ValueError):
            find_session(self.home, self.sessions)

    def test_trixie_pi_desktop_is_preferred_over_bare_labwc(self):
        (self.sessions / "labwc.desktop").write_text("[Desktop Entry]\nExec=labwc\n")
        (self.sessions / "rpd-labwc.desktop").write_text("[Desktop Entry]\nExec=/usr/bin/labwc-pi\n")
        self.assertEqual(find_session(self.home, self.sessions), "rpd-labwc")


if __name__ == "__main__":
    unittest.main()
