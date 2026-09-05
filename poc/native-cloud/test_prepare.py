"""Kiểm tra chuẩn bị APK bằng dữ liệu giả, không cần mạng hoặc APK thật."""

import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from prepare import LIBRARIES, prepare


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.smali = self.root / "SmartApplication.smali"
        self.smali.write_text(
            'const-string v0, "' + "A" * 20 + '"\n'
            'const-string v1, "' + "B" * 32 + '"\n',
            encoding="utf-8",
        )
        self.apk = self.root / "abi.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            for name in LIBRARIES:
                archive.writestr(f"lib/armeabi-v7a/{name}", b"\x7fELF\x01test")
            archive.writestr("../../escape", "must-not-extract")
        self.output = self.root / "private"

    def test_private_permissions_and_allowlisted_members(self):
        prepare(self.smali, self.apk, self.output)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual(
            stat.S_IMODE((self.output / "app-credentials").stat().st_mode), 0o600
        )
        self.assertEqual(
            {path.name for path in (self.output / "libs").iterdir()}, set(LIBRARIES)
        )
        self.assertFalse((self.root / "escape").exists())

    def test_existing_output_not_overwritten(self):
        self.output.mkdir()
        marker = self.output / "app-credentials"
        marker.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            prepare(self.smali, self.apk, self.output)
        self.assertEqual(marker.read_text(), "existing")

    def test_unrelated_twenty_character_string_is_ignored(self):
        with self.smali.open("a", encoding="utf-8") as source:
            source.write('const-string v2, "' + "C" * 20 + '"\n')
        prepare(self.smali, self.apk, self.output)
        self.assertEqual(
            (self.output / "app-credentials").read_text(),
            "A" * 20 + "\n" + "B" * 32 + "\n",
        )

    def test_ambiguous_pairs_fail_closed(self):
        with self.smali.open("a", encoding="utf-8") as source:
            source.write('const-string v2, "' + "C" * 20 + '"\n')
            source.write('const-string v3, "' + "D" * 32 + '"\n')
        with self.assertRaises(ValueError):
            prepare(self.smali, self.apk, self.output)
        self.assertFalse(self.output.exists())

    def test_unknown_credentials_fail_closed(self):
        self.smali.write_text("unrecognized layout", encoding="utf-8")
        with self.assertRaises(ValueError):
            prepare(self.smali, self.apk, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_library_fails_before_writing(self):
        with zipfile.ZipFile(self.apk, "w"):
            pass
        with self.assertRaises(KeyError):
            prepare(self.smali, self.apk, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
