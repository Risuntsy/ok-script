import numpy as np
import cv2
import mmap
import os
import select
import threading
from .base import BaseCaptureMethod
from ok.util.logger import Logger
from ok.device.wlroots.connection import WaylandConnection

logger = Logger.get_logger(__name__)

class WlrootsCaptureMethod(BaseCaptureMethod):
    name = "Wlroots Capture"

    def __init__(self, hwnd=None, socket_name=None):
        super().__init__()
        self.socket_name = socket_name
        self.connection = None
        self.frame_data = None
        self._fd = -1
        self._shm_pool = None
        self._buffer = None
        self._width = 0
        self._height = 0
        self._stride = 0
        self._format = None
        self._buffer_size = 0
        self._frame_ready = False
        self._capture_lock = threading.Lock()

    def connected(self):
        return self.connection is not None and self.connection.connected()

    def get_abs_cords(self, x, y):
        # On wlroots the entire output is captured, coordinates are already in screen space
        return x, y

    def start_or_stop(self):
        try:
            self.connection = WaylandConnection.get(self.socket_name)
            self.socket_name = self.connection.socket_name
            return self.connected()
        except Exception as e:
            self.connection = None
            logger.error(f'WlrootsCaptureMethod: {e}')
            return False

    def close(self):
        self._cleanup_buffer()
        if self.connection:
            self.connection.disconnect()
            self.connection = None

    def _cleanup_buffer(self):
        if self._buffer:
            self._buffer.destroy()
            self._buffer = None
        if self._shm_pool:
            self._shm_pool.destroy()
            self._shm_pool = None
        if self.frame_data:
            self.frame_data.close()
            self.frame_data = None
        if self._fd != -1:
            os.close(self._fd)
            self._fd = -1

    def _create_buffer(self, width, height, stride, format_modifier):
        self._cleanup_buffer()
        self._width = width
        self._height = height
        self._stride = stride
        self._format = format_modifier
        self._buffer_size = stride * height

        # Create anonymous file for SHM
        import tempfile
        try:
            fd = os.memfd_create("screencopy", getattr(os, "MFD_CLOEXEC", 0))
        except AttributeError:
            fd, path = tempfile.mkstemp(dir='/dev/shm', prefix='ok-screencopy-')
            os.unlink(path)

        os.ftruncate(fd, self._buffer_size)
        self._fd = fd

        self.frame_data = mmap.mmap(fd, self._buffer_size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        self._shm_pool = self.connection.shm.create_pool(fd, self._buffer_size)
        self._buffer = self._shm_pool.create_buffer(0, width, height, stride, format_modifier)

    def do_get_frame(self):
        with self._capture_lock:
            return self._do_get_frame_locked()

    def _do_get_frame_locked(self):
        if self.exit_event and self.exit_event.is_set():
            return None
        if not self.connection or not self.connection.outputs:
            return None

        # Capture first output for now
        output = self.connection.outputs[0]
        frame = self.connection.screencopy_manager.capture_output(0, output)

        self._frame_ready = False

        def _on_buffer(frame, format, width, height, stride):
            if width != self._width or height != self._height or stride != self._stride:
                self._create_buffer(width, height, stride, format)
            if self.connection.screencopy_version < 3:
                frame.copy(self._buffer)
                self.connection.display.flush()

        def _on_buffer_done(frame):
            frame.copy(self._buffer)
            self.connection.display.flush()

        def _on_ready(frame, tv_sec_hi, tv_sec_lo, tv_nsec):
            self._frame_ready = True
            frame.destroy()

        def _on_failed(frame):
            logger.error("Screencopy failed")
            frame.destroy()

        frame.dispatcher['buffer'] = _on_buffer
        frame.dispatcher['buffer_done'] = _on_buffer_done
        frame.dispatcher['ready'] = _on_ready
        frame.dispatcher['failed'] = _on_failed

        self.connection.display.flush()

        # Poll so shutdown can interrupt frame capture before disconnecting.
        try:
            import time
            start_time = time.monotonic()
            deadline = start_time + 2.0
            while not self._frame_ready and time.monotonic() < deadline:
                if self.exit_event and self.exit_event.is_set():
                    return None
                display = self.connection.display
                timeout = min(0.05, max(0, deadline - time.monotonic()))
                readable, _, exceptional = select.select(
                    [display.get_fd()], [], [display.get_fd()], timeout)
                if exceptional:
                    raise ConnectionError("Wayland display connection failed")
                if readable:
                    display.dispatch(block=True)
        except Exception as e:
            if self.exit_event and self.exit_event.is_set() and 'Cannot find display' in str(e):
                logger.debug(f"Wayland dispatch stopped during shutdown: {e}")
            else:
                logger.error(f"Error dispatching wayland events: {e}")

        logger.debug(f"Wlroots do_get_frame _frame_ready: {self._frame_ready}, frame_data is None: {self.frame_data is None}")
        if not self._frame_ready or not self.frame_data:
            return None

        # Convert raw pixel buffer to numpy array
        arr = np.frombuffer(self.frame_data, dtype=np.uint8).reshape((self._height, self._stride // 4, 4))

        # Crop to actual width if stride includes padding
        if self._stride // 4 != self._width:
            arr = arr[:, :self._width, :]

        # wl_shm format determines channel order in memory (little-endian)
        # XRGB8888 -> BGRA in memory, XBGR8888 -> RGBA in memory
        # We only need 3 channels, so drop the alpha/X channel
        if self._format == 1:  # WL_SHM_FORMAT_XRGB8888
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        elif self._format == 875709016:  # WL_SHM_FORMAT_XBGR8888
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        else:
            # Fallback: try BGRA2BGR, but log unknown format
            logger.warning(f"Unknown wl_shm format {self._format}, assuming BGRA")
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
