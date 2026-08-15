import os
import select
import threading
from pywayland.client import Display
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

# Note: These protocols will be generated in ok/device/wlroots/protocols/
from .protocols.wlr_screencopy_unstable_v1 import ZwlrScreencopyManagerV1
from .protocols.wlr_foreign_toplevel_management_unstable_v1 import ZwlrForeignToplevelManagerV1
from .protocols.wlr_virtual_pointer_unstable_v1 import ZwlrVirtualPointerManagerV1
from .protocols.virtual_keyboard_unstable_v1 import ZwpVirtualKeyboardManagerV1
from pywayland.protocol.wayland import WlSeat, WlOutput, WlShm

class WaylandConnection:
    """
    Opens and owns the Wayland socket connection.

    Socket selection priority:
      1. Explicit `socket_name` argument selected by the user
      2. Auto-discovery: the first compatible socket from all wayland-N sockets
      3. $WAYLAND_DISPLAY env var fallback

    Discovers all required wlroots protocol globals from wl_registry.
    """
    _instance: 'WaylandConnection | None' = None
    _lock = threading.Lock()
    _dispatch_lock = threading.Lock()

    def __init__(self):
        self.socket_name: str = ''       # which socket we are connected to
        self.display: Display = None
        self.screencopy_manager: ZwlrScreencopyManagerV1 = None
        self.screencopy_version = 0
        self.toplevel_manager: ZwlrForeignToplevelManagerV1 = None
        self.vp_manager: ZwlrVirtualPointerManagerV1 = None
        self.vk_manager: ZwpVirtualKeyboardManagerV1 = None
        self.seat: WlSeat = None
        self.shm: WlShm = None
        self.outputs: list[WlOutput] = []
        self.toplevels: list = []
        self._missing: list[str] = []
        self.closing = False

    # ------------------------------------------------------------------
    # Connection & discovery
    # ------------------------------------------------------------------

    @staticmethod
    def list_available_sockets() -> list[str]:
        """
        Return all Wayland socket names found in $XDG_RUNTIME_DIR,
        sorted highest-number first so nested sessions appear first.
        """
        from ok.util.wayland import discover_sockets
        return discover_sockets()

    @classmethod
    def list_supported_sockets(cls) -> list[dict]:
        """Probe every discovered socket and describe those usable by wlroots capture."""
        supported = []
        for socket_name in cls.list_available_sockets():
            connection = cls()
            try:
                connection.connect(socket_name)
                output = connection.outputs[0]
                nick = "Wayland Desktop"
                titles = []
                for toplevel in connection.toplevels:
                    title = getattr(toplevel, 'title', '')
                    app_id = getattr(toplevel, 'app_id', '')
                    if title:
                        titles.append(title)
                    if (title or app_id) and nick == "Wayland Desktop":
                        nick = title or app_id
                supported.append({
                    'socket_name': socket_name,
                    'nick': nick,
                    'width': getattr(output, 'width', 1920) or 1920,
                    'height': getattr(output, 'height', 1080) or 1080,
                    'titles': titles,
                })
            except Exception as e:
                logger.debug(
                    f'WaylandConnection: socket {socket_name} is not a supported wlroots socket: {e}')
            finally:
                connection.disconnect()
        return supported

    def connect(self, socket_name: str | None = None):
        """
        Connect to a Wayland compositor socket.

        Parameters
        ----------
        socket_name:
            Explicit socket name (e.g. 'wayland-2') for manual override.
            If None, auto-discovery selects the first socket that accepts a
            connection and exposes all required protocols.
        """
        candidates = [socket_name] if socket_name else self.list_available_sockets()
        last_err = None
        for name in candidates:
            self.closing = False
            self._reset_globals()
            try:
                display = Display(name)
                display.connect()
                self.display = display
                self.socket_name = name
                registry = self.display.get_registry()
                registry.dispatcher['global'] = self._on_global
                self.display.roundtrip()
                if self.outputs:
                    self.display.roundtrip()
                self._check_required()
                logger.info(f'WaylandConnection: connected to supported socket {name}')
                return
            except Exception as e:
                logger.debug(f'WaylandConnection: failed to connect to {name}: {e}')
                last_err = e
                self.disconnect()
        raise WlrootsUnsupportedError(
            f'Could not connect to a supported Wayland socket. '
            f'Tried: {candidates}. Last error: {last_err}')

    def reconnect(self, socket_name: str):
        """
        Switch to a different socket (e.g. after user changes selection in GUI).
        Closes the current connection first.
        """
        self.disconnect()
        self._reset_globals()
        self.connect(socket_name)

    def _reset_globals(self):
        self.screencopy_manager = None
        self.screencopy_version = 0
        self.toplevel_manager = None
        self.vp_manager = None
        self.vk_manager = None
        self.seat = None
        self.shm = None
        self.outputs = []
        self.toplevels = []
        self._missing = []

    # ------------------------------------------------------------------
    # Registry callbacks
    # ------------------------------------------------------------------

    def _on_global(self, registry, name, interface, version):
        if interface == 'zwlr_screencopy_manager_v1':
            self.screencopy_version = min(version, 3)
            self.screencopy_manager = registry.bind(
                name, ZwlrScreencopyManagerV1, self.screencopy_version)
        elif interface == 'zwlr_foreign_toplevel_manager_v1':
            self.toplevel_manager = registry.bind(name, ZwlrForeignToplevelManagerV1, min(version, 3))
            self.toplevel_manager.dispatcher['toplevel'] = self._on_toplevel
        elif interface == 'zwlr_virtual_pointer_manager_v1':
            self.vp_manager = registry.bind(name, ZwlrVirtualPointerManagerV1, min(version, 2))
        elif interface == 'zwp_virtual_keyboard_manager_v1':
            self.vk_manager = registry.bind(name, ZwpVirtualKeyboardManagerV1, 1)
        elif interface == 'wl_seat':
            self.seat = registry.bind(name, WlSeat, min(version, 7))
        elif interface == 'wl_shm':
            self.shm = registry.bind(name, WlShm, 1)
        elif interface == 'wl_output':
            if self.closing:
                return
            output = registry.bind(name, WlOutput, min(version, 4))
            output.width = 0
            output.height = 0
            output._done = False

            def _on_mode(proxy, flags, width, height, refresh):
                if self.closing:
                    return
                if flags & WlOutput.mode.current:
                    output.width = width
                    output.height = height

            def _on_done(proxy):
                if self.closing:
                    return
                output._done = True

            output.dispatcher['mode'] = _on_mode
            output.dispatcher['done'] = _on_done
            self.outputs.append(output)

    def _on_toplevel(self, manager, toplevel):
        """Callback when the compositor announces a new toplevel window."""
        if self.closing:
            return
        # Store mutable state directly on the proxy so DeviceManager can read it
        toplevel.app_id = ''
        toplevel.title = ''
        toplevel._done = False

        def _on_title(handle, title):
            if self.closing:
                return
            handle.title = title

        def _on_app_id(handle, app_id):
            if self.closing:
                return
            handle.app_id = app_id

        def _on_closed(handle):
            if self.closing:
                return
            if handle in self.toplevels:
                self.toplevels.remove(handle)

        def _on_done(handle):
            if self.closing:
                return
            handle._done = True

        toplevel.dispatcher['title'] = _on_title
        toplevel.dispatcher['app_id'] = _on_app_id
        toplevel.dispatcher['closed'] = _on_closed
        toplevel.dispatcher['done'] = _on_done
        self.toplevels.append(toplevel)
        logger.debug(f'WaylandConnection: new toplevel handle added')

    def _check_required(self):
        required = {
            'zwlr_screencopy_manager_v1': self.screencopy_manager,
            'wl_shm': self.shm,
            'wl_seat': self.seat,
            'wl_output': self.outputs[0] if self.outputs else None,
        }
        self._missing = [k for k, v in required.items() if v is None]
        if self._missing:
            raise WlrootsUnsupportedError(
                f'Socket "{self.socket_name}" is missing required wlroots protocols: '
                f'{self._missing}. '
                f'This framework only supports wlroots compositors (Sway, Hyprland, labwc, etc.).'
            )

    # ------------------------------------------------------------------
    # Runtime helpers
    # ------------------------------------------------------------------

    def connected(self) -> bool:
        """Return whether the compositor socket is still usable."""
        if self.closing or self.display is None:
            return False
        try:
            fd = self.display.get_fd()
            poller = select.poll()
            poller.register(fd, select.POLLERR | select.POLLHUP | select.POLLNVAL)
            return not poller.poll(0)
        except Exception as e:
            logger.debug(f'WaylandConnection: connection check failed: {e}')
            return False

    def dispatch(self):
        """Process pending Wayland events. Call regularly from capture thread."""
        if self.closing or self.display is None:
            return
        with self._dispatch_lock:
            if self.closing or self.display is None:
                return
            self.display.dispatch(block=False)
            self.display.flush()

    def disconnect(self):
        self.closing = True
        if self.display:
            try:
                # Drain pending events while the display is still valid so
                # pywayland callbacks do not raise "Cannot find display".
                try:
                    self.display.roundtrip()
                except Exception:
                    pass
                self.display.disconnect()
            except Exception as e:
                logger.debug(f'WaylandConnection: disconnect ignored error: {e}')
            finally:
                self.display = None
                self._reset_globals()
                if type(self)._instance is self:
                    type(self)._instance = None

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, socket_name: str | None = None) -> 'WaylandConnection':
        """
        Return the singleton connection, creating it on first call.

        Pass `socket_name` to force a specific socket on first creation,
        or call `reconnect()` on an existing instance to switch sockets.
        """
        with cls._lock:
            if cls._instance is None:
                connection = WaylandConnection()
                connection.connect(socket_name)
                cls._instance = connection
            elif not cls._instance.connected():
                cls._instance.disconnect()
                connection = WaylandConnection()
                connection.connect(socket_name)
                cls._instance = connection
            elif socket_name and cls._instance.socket_name != socket_name:
                # User switched socket via GUI — reconnect
                cls._instance.reconnect(socket_name)
        return cls._instance


class WlrootsUnsupportedError(RuntimeError):
    """Raised when the compositor does not expose required wlroots protocols."""
