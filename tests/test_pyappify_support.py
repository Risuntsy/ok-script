import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ok.util.pyappify_support import parse_pyappify_version, supports_update_check


class TestParsePyappifyVersion(unittest.TestCase):
    def test_parses_plain_and_prefixed_versions(self):
        self.assertEqual((1, 2, 2), parse_pyappify_version("1.2.2"))
        self.assertEqual((1, 2, 2), parse_pyappify_version("v1.2.2"))

    def test_rejects_unset_and_malformed_versions(self):
        for version in (None, "", "v", "1.2.2b1", "dev", 122):
            self.assertIsNone(parse_pyappify_version(version), version)


class TestSupportsUpdateCheck(unittest.TestCase):
    def test_running_from_source_disables_update_check(self):
        # No PyAppify launcher started the app, so PYAPPIFY_VERSION is unset.
        module = SimpleNamespace(get_version_list=Mock(), pyappify_version=None)
        self.assertFalse(supports_update_check(module))
        module.get_version_list.assert_not_called()

    def test_launcher_older_than_the_version_api_disables_update_check(self):
        module = SimpleNamespace(get_version_list=Mock(), pyappify_version="1.2.1")
        self.assertFalse(supports_update_check(module))

    def test_supported_launcher_enables_update_check(self):
        module = SimpleNamespace(get_version_list=Mock(), pyappify_version="v1.2.2")
        self.assertTrue(supports_update_check(module))

    def test_missing_api_disables_update_check(self):
        self.assertFalse(supports_update_check(SimpleNamespace()))

    def test_module_without_version_attribute_keeps_previous_behaviour(self):
        self.assertTrue(supports_update_check(SimpleNamespace(get_version_list=Mock())))


class TestAboutTabUpdateCardGate(unittest.TestCase):
    def _about_tab(self, module):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from ok.ui.qt.about.AboutTab import AboutTab

        QApplication.instance() or QApplication([])
        return AboutTab({
            "gui_icon": ":/icon/icon.ico",
            "gui_title": "demo",
            "version": "v1.1.0",
            "debug": False,
        }, pyappify_module=module)

    def test_no_update_card_without_a_launcher(self):
        tab = self._about_tab(SimpleNamespace(
            app_version="v1.1.0", get_version_list=Mock(), pyappify_version=None))
        self.assertIsNone(tab.update_card)

    def test_update_card_with_a_supported_launcher(self):
        tab = self._about_tab(SimpleNamespace(
            app_version="v1.1.0", get_version_list=Mock(), pyappify_version="1.2.2"))
        self.assertIsNotNone(tab.update_card)


if __name__ == "__main__":
    unittest.main()
