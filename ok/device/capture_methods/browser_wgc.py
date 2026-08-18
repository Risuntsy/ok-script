import sys
if sys.platform != "win32":
    raise ImportError(f"{__file__} is Windows-only")

import win32gui
from ok.device.capture_methods.bitblt_utils import get_crop_point
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod

class BrowserWindowAdapter:
    def __init__(self, capture):
        self.capture = capture

    @property
    def hwnd(self):
        return self.capture.hwnd

    @property
    def exists(self):
        return self.capture.connected() and self.capture.hwnd > 0

    @property
    def app_exit_event(self):
        return self.capture.exit_event

    @property
    def width(self):
        return self.capture.width

    @property
    def height(self):
        return self.capture.height

    @property
    def exe_full_path(self):
        return self.capture.exe_full_path

    @property
    def capture_target_signature(self):
        return (
            self.hwnd,
            self.width,
            self.height,
            self.capture.x_offset,
            self.capture.y_offset,
            self.capture.exe_full_path,
        )

    def get_abs_cords(self, x, y):
        try:
            rect = win32gui.GetWindowRect(self.capture.hwnd)
            return rect[0] + self.capture.x_offset + x, rect[1] + self.capture.y_offset + y
        except:
            return x, y


class BrowserWGC(WindowsGraphicsCaptureMethod):
    def __init__(self, browser_method):
        self.browser_method = browser_method
        super().__init__(BrowserWindowAdapter(browser_method))

    def crop_image(self, frame):
        if frame is None:
            return None

        fh, fw = frame.shape[:2]
        target_w = int(getattr(self.hwnd_window, "width", 0) or 0)
        target_h = int(getattr(self.hwnd_window, "height", 0) or 0)
        if target_w <= 0 or target_h <= 0:
            return frame

        x = int(getattr(self.browser_method, "x_offset", 0) or 0)
        y = int(getattr(self.browser_method, "y_offset", 0) or 0)

        if 0 <= x and 0 <= y and x + target_w <= fw and y + target_h <= fh:
            left_extra = x
            right_extra = fw - (x + target_w)
            top_extra = y
            bottom_extra = fh - (y + target_h)
            if abs(left_extra - right_extra) <= 2 and abs(bottom_extra - left_extra) <= 2:
                return frame[y:y + target_h, x:x + target_w]

        border, title_height = get_crop_point(fw, fh, target_w, target_h)
        border = max(0, int(border))
        title_height = max(0, int(title_height))
        if border == 0 and title_height == 0:
            return frame

        x1 = border
        y1 = title_height
        x2 = fw - border
        y2 = fh - border
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]
