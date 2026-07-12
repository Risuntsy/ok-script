import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import ok.gui.wlroots.PreviewDialog as preview_module
from ok.gui.wlroots.PreviewDialog import WlrootsPreviewDialog, WlrootsPreviewWidget, _FrameWorker


class FakeCapture:
    def __init__(self, frame=None):
        self.frame = frame

    def get_frame(self):
        return self.frame


class TestWlrootsPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_widget_stores_frame_size_from_image(self):
        from PySide6.QtGui import QImage

        widget = WlrootsPreviewWidget()
        image = QImage(320, 180, QImage.Format_RGB888)

        widget.set_image(image)

        self.assertEqual(320, widget.frame_width)
        self.assertEqual(180, widget.frame_height)

    def test_frame_worker_emits_none_status_for_empty_frame(self):
        worker = _FrameWorker()
        results = []
        worker.frame_ready.connect(lambda image, message: results.append((image, message)))

        worker._capture_frame(FakeCapture(None))

        self.assertEqual(1, len(results))
        self.assertIsNone(results[0][0])
        self.assertEqual("Frame capture returned None", results[0][1])

    def test_frame_worker_converts_bgr_frame_to_qimage_copy(self):
        worker = _FrameWorker()
        results = []
        worker.frame_ready.connect(lambda image, message: results.append((image, message)))
        frame = np.zeros((10, 20, 3), dtype=np.uint8)

        worker._capture_frame(FakeCapture(frame))

        self.assertEqual(1, len(results))
        image, message = results[0]
        self.assertEqual(20, image.width())
        self.assertEqual(10, image.height())
        self.assertEqual("20x10", message)

    def test_is_available_requires_linux_wayland_device(self):
        fake_og = SimpleNamespace(
            device_manager=SimpleNamespace(get_preferred_device=lambda: {"device": "wayland"})
        )

        with patch.object(preview_module, "og", fake_og), patch.object(preview_module.sys, "platform", "linux"):
            self.assertTrue(WlrootsPreviewDialog.is_available())

    def test_is_available_rejects_non_wayland_device(self):
        fake_og = SimpleNamespace(
            device_manager=SimpleNamespace(get_preferred_device=lambda: {"device": "windows"})
        )

        with patch.object(preview_module, "og", fake_og), patch.object(preview_module.sys, "platform", "linux"):
            self.assertFalse(WlrootsPreviewDialog.is_available())


if __name__ == '__main__':
    unittest.main()
