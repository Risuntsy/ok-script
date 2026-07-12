import sys
import threading

import cv2
from PySide6.QtCore import QObject, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel

from ok import og
from ok.gui.widget.FramelessDialog import FramelessDialog
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class WlrootsPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.frame_width = 0
        self.frame_height = 0
        self.paint_rect = QRectF()
        self.setMinimumSize(640, 360)

    def sizeHint(self):
        return QSize(960, 540)

    def set_image(self, image):
        self.image = image
        if image is not None:
            self.frame_width = image.width()
            self.frame_height = image.height()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 20, 24))

        if self.image is None or self.image.isNull():
            self.paint_rect = QRectF()
            return

        image_size = self.image.size()
        scaled_size = image_size.scaled(self.size(), Qt.KeepAspectRatio)
        x = (self.width() - scaled_size.width()) / 2
        y = (self.height() - scaled_size.height()) / 2
        self.paint_rect = QRectF(x, y, scaled_size.width(), scaled_size.height())
        painter.drawImage(self.paint_rect, self.image)


class _FrameWorker(QObject):
    frame_ready = Signal(object, str)

    def __init__(self):
        super().__init__()
        self.running = False
        self._lock = threading.Lock()

    def request_frame(self, capture):
        with self._lock:
            if self.running:
                return False
            self.running = True
        thread = threading.Thread(target=self._capture_frame, args=(capture,), name="WlrootsPreview", daemon=True)
        thread.start()
        return True

    def _capture_frame(self, capture):
        image = None
        message = ""
        try:
            frame = capture.get_frame()
            if frame is None:
                message = "Frame capture returned None"
            else:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channels = rgb_frame.shape
                bytes_per_line = channels * width
                image = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888).copy()
                message = f"{width}x{height}"
        except Exception as e:
            message = str(e)
            logger.error(f"wlroots preview capture failed: {e}", e)
        finally:
            with self._lock:
                self.running = False
            self.frame_ready.emit(image, message)


class WlrootsPreviewDialog(FramelessDialog):
    REFRESH_INTERVAL_MS = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Wayland Preview"))
        self.resize(980, 620)
        self.preview_widget = WlrootsPreviewWidget(self)
        self.status_label = CaptionLabel("", self)
        self.title_label = BodyLabel(self.tr("Wayland Preview"), self)
        self.worker = _FrameWorker()
        self.worker.frame_ready.connect(self._on_frame_ready)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_frame)

        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 48, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addWidget(self.preview_widget, stretch=1)
        layout.addWidget(self.status_label)
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(content)

        self._refresh_frame()
        self.timer.start(self.REFRESH_INTERVAL_MS)

    @staticmethod
    def is_available():
        if sys.platform != "linux":
            return False
        device = og.device_manager.get_preferred_device()
        return device is not None and device.get("device") == "wayland"

    @staticmethod
    def _get_capture():
        try:
            from ok.device.capture_methods.wlroots import WlrootsCaptureMethod
        except Exception:
            return None, "Wlroots capture is unavailable"

        capture = og.device_manager.capture_method
        if not isinstance(capture, WlrootsCaptureMethod):
            return None, "Current capture method is not Wlroots"
        if not capture.connected():
            return None, "Wlroots capture is not connected"
        return capture, ""

    def _refresh_frame(self):
        if not self.isVisible() and self.timer.isActive():
            return
        if not self.is_available():
            self.status_label.setText(self.tr("No Wayland device selected"))
            return
        capture, message = self._get_capture()
        if capture is None:
            self.status_label.setText(self.tr(message))
            return
        self.worker.request_frame(capture)

    def _on_frame_ready(self, image, message):
        if image is not None:
            self.preview_widget.set_image(image)
        self.status_label.setText(self.tr(message) if message else "")

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_frame()
        if not self.timer.isActive():
            self.timer.start(self.REFRESH_INTERVAL_MS)

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
