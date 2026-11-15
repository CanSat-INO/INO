"""ROS 2・Gazebo環境診断の回帰テスト。"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ros_gazebo_diagnostics as diag
from ros_gazebo_diagnostics_gui import RosGazeboDiagnosticsTab


class DiagnosticsTests(unittest.TestCase):

    def test_ros_and_gazebo_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(diag.shutil, "which", return_value=None):
                result = diag.diagnose(Path(tmp))

        self.assertEqual(result["ros2"], "not_detected")
        self.assertEqual(result["gazebo"], "not_detected")

    def test_gazebo_without_ros(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                diag.shutil,
                "which",
                side_effect=lambda name: "/usr/bin/gz" if name == "gz" else None,
            ):
                result = diag.diagnose(Path(tmp))

        self.assertEqual(result["ros2"], "not_detected")
        self.assertEqual(result["gazebo"], "command_detected")

    def test_ros_and_gazebo_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            setup = Path(tmp) / "lyrical" / "setup.bash"
            setup.parent.mkdir()
            setup.write_text("# test\n")

            fake = subprocess.CompletedProcess(
                [],
                0,
                "DISTRO=lyrical\nROS2=available\nGAZEBO=detected\n",
                "",
            )

            with patch.object(diag.subprocess, "run", return_value=fake):
                with patch.object(diag, "check_package", return_value=True):
                    result = diag.diagnose(Path(tmp))

        self.assertEqual(result["ros2"], "available_after_setup")
        self.assertEqual(result["gazebo"], "command_detected")
        self.assertTrue(result["ros_gz_bridge"])

    def test_ros_setup_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            setup = Path(tmp) / "lyrical" / "setup.bash"
            setup.parent.mkdir()
            setup.write_text("# test\n")

            fake = subprocess.CompletedProcess([], 9, "", "error")

            with patch.object(diag.subprocess, "run", return_value=fake):
                result = diag.diagnose(Path(tmp))

        self.assertEqual(result["ros2"], "not_detected")
        self.assertTrue(result["notes"])

    def test_ros_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            setup = Path(tmp) / "lyrical" / "setup.bash"
            setup.parent.mkdir()
            setup.write_text("# test\n")

            with patch.object(
                diag.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("bash", 20),
            ):
                result = diag.diagnose(Path(tmp))

        self.assertEqual(result["ros2"], "not_detected")
        self.assertTrue(
            any("タイムアウト" in note for note in result["notes"])
        )

    def test_gui_report(self):
        report = RosGazeboDiagnosticsTab.format_report({
            "wsl": True,
            "python": "3.14.4",
            "ros2": "available_after_setup",
            "ros_distro": "lyrical",
            "gazebo": "command_detected",
            "ros_gz_bridge": True,
            "colcon": True,
        })

        self.assertIn("lyrical", report)
        self.assertIn("コマンド検出", report)
        self.assertIn("colcon", report)
        self.assertIn("起動は未検証", report)


if __name__ == "__main__":
    unittest.main()
