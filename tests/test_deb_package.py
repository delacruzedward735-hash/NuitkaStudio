# SPDX-License-Identifier: MIT
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from nuitka_gui.deb_package import DebianPackageConfig, build_debian_package


@unittest.skipUnless(shutil.which("dpkg-deb") and os.name != "nt", "dpkg-deb is required")
class DebianPackageTests(unittest.TestCase):
    def test_builds_installable_standalone_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = root / "NexaConvert.dist"
            dist.mkdir()
            executable = dist / "NexaConvert"
            executable.write_bytes(b"\x7fELFdemo")
            executable.chmod(0o755)
            (dist / "support.so").write_bytes(b"support")
            icon = root / "icon.png"
            icon.write_bytes(b"png")

            package = build_debian_package(
                DebianPackageConfig(
                    executable=executable,
                    output_directory=root / "output",
                    package_id="nexaconvert",
                    application_name="NexaConvert",
                    version="1.2.3.4",
                    maintainer="John Edward Dela Cruz",
                    description="Universal converter",
                    icon_path=icon,
                    mode="standalone",
                )
            )

            self.assertTrue(package.is_file())
            self.assertTrue(package.name.startswith("nexaconvert_1.2.3.4_"))
            fields = subprocess.run(
                ["dpkg-deb", "--field", str(package), "Package", "Version"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertIn("nexaconvert", fields)
            self.assertIn("1.2.3.4", fields)
            contents = subprocess.run(
                ["dpkg-deb", "--contents", str(package)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertIn("./opt/nexaconvert/NexaConvert", contents)
            self.assertIn("./opt/nexaconvert/support.so", contents)
            self.assertIn("./usr/share/applications/nexaconvert.desktop", contents)
            self.assertIn("./usr/bin/nexaconvert", contents)


if __name__ == "__main__":
    unittest.main()
