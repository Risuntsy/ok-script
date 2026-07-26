# wlroots Wayland Support

## Scope

`ok-script` supports Linux automation on Wayland compositors that expose the
required wlroots protocols. This backend is independent from the Windows, browser,
and ADB device paths.

```text
DeviceManager
  |-- windows -> HwndWindow + Windows capture and interaction
  |-- wayland -> WlrootsCaptureMethod + WlrootsInteraction
  |-- browser -> BrowserCaptureMethod + BrowserInteraction
  `-- adb     -> ADBCaptureMethod + ADBInteraction
```

GNOME Mutter and KDE KWin sessions are not supported by this backend. Portal,
PipeWire, and D-Bus capture are not part of the wlroots device path.

## Requirements

Linux installs `pywayland>=0.4.18` through the platform marker in `setup.py`.

The selected compositor socket must expose:

- `zwlr_screencopy_manager_v1`
- `wl_shm`
- `wl_seat`
- at least one `wl_output`

Pointer automation requires `zwlr_virtual_pointer_manager_v1`. Keyboard automation
requires `zwp_virtual_keyboard_manager_v1`. The foreign-toplevel protocol is used
when available to provide a display name, but capture still targets an output.

## Components

| Component | Path |
|---|---|
| Socket discovery | `ok/util/wayland.py` |
| Wayland registry and connection | `ok/device/wlroots/connection.py` |
| Protocol bindings | `ok/device/wlroots/protocols/` |
| Output capture | `ok/device/capture_methods/wlroots.py` |
| Pointer and keyboard input | `ok/device/interaction_methods/wlroots.py` |
| Evdev key mapping | `ok/device/interaction_methods/evdev_keys.py` |
| Device selection | `ok/device/DeviceManager.py` |

## Connection Lifecycle

Constructing `DeviceManager` does not open a Wayland socket. Device refresh probes
the discovered sockets with short-lived connections. Starting a selected device
creates the shared runtime connection lazily through `WaylandConnection.get()`.

Socket discovery scans `$XDG_RUNTIME_DIR/wayland-*`, keeps actual socket files, and
sorts them by descending numeric suffix. Every socket is registry-probed, and every
socket exposing the required protocols is returned to the device list. Unsupported
sockets are omitted. If no socket file is found, discovery probes `$WAYLAND_DISPLAY`
or `wayland-0` as a fallback.

`WaylandConnection` is a process-wide singleton shared by capture and interaction.
Its registry binds screencopy, shared memory, seat, output, virtual input, and
foreign-toplevel globals. `connected()` polls the display descriptor for connection
errors. Disconnect resets the singleton and all bound globals.

### Socket Discovery And Selection

`WaylandConnection.list_supported_sockets()` returns every compatible socket as a
list of dictionaries:

```python
[
    {
        "socket_name": "wayland-2",
        "nick": "Wuthering Waves",
        "width": 1920,
        "height": 1080,
    },
    {
        "socket_name": "wayland-1",
        "nick": "Wayland Desktop",
        "width": 2560,
        "height": 1440,
    },
]
```

The descending numeric order only controls display order and the default fallback;
it does not restrict selection to the largest suffix. `DeviceManager` converts every
entry into a device with an identifier such as `wayland_wayland-2` and keeps the
socket name in both `socket` and `address`. Selecting a row stores that unique device
identifier as the preferred device. On start, `WlrootsCaptureMethod` receives the
selected socket name explicitly.

Sockets that cannot be opened, lack screencopy, shared memory, a seat, or an output
are not returned. Pointer and keyboard availability is still reported by the
corresponding optional protocol managers after connection.

## Device Model

Each compatible socket appears as a separate `wayland` device, identified by its
socket name. The Start tab can freely select any returned device, and the preferred
device persists through its unique identifier. Switching devices closes the old
capture and virtual-input objects before connecting to the newly selected socket.
Each device resolution comes from that socket's first `wl_output`. A title or app ID
from the first advertised toplevel may be included in the display name; this does
not change the capture target.

Linux does not create `HwndWindow` or run the Windows window-size monitor. Windows
capture, interaction, DPI, process, task-scheduler, and audio behavior remains
isolated to Windows.

## Capture

`WlrootsCaptureMethod` captures the first advertised output through
`zwlr_screencopy_manager_v1`:

1. Request an output frame.
2. Allocate or resize a shared-memory buffer from the compositor's format, width,
   height, and stride.
3. Poll the Wayland display in short intervals for up to two seconds.
4. Stop polling immediately when the shared exit event is set.
5. Convert XRGB8888 or XBGR8888 shared memory into a BGR NumPy frame.

A capture lock serializes frame requests because the backend owns one shared
Wayland display connection.

Capture coordinates are output coordinates. The backend does not crop to a window
or translate through window geometry.

## Interaction

`WlrootsInteraction` creates a virtual pointer and virtual keyboard from the shared
connection. It supports:

- absolute pointer movement using the captured output dimensions
- left, right, and middle click
- pointer down and up
- scroll and swipe
- key press, key down, and key up
- common keyboard keys and F1-F12 through the evdev mapping

Button presses enforce a minimum down time. Keyboard initialization installs a
self-contained XKB keymap through a shared-memory file descriptor. Shutdown destroys
the virtual devices and closes the keymap descriptor.

## Limits

- Only compositors exposing the required wlroots protocols are supported.
- Capture uses the first output and includes the whole output.
- Multi-output selection is not exposed.
- Only sockets that pass the required-protocol probe appear in the device list.
- Window-level crop, geometry, resize, activation, and foreground control are not available.
- Linux game launch, scheduled tasks, and background audio controls are not available.

## Validation

Run validation through the repository-local virtual environment:

```bash
./.venv/bin/python -m compileall -q ok
QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m unittest -q \
  tests.test_capture_update \
  tests.test_wayland_socket_selection
```

Protocol behavior that depends on a real compositor must be verified in the target
wlroots session. Unit tests cover frame conversion, capture retry, and capture
cleanup behavior.
