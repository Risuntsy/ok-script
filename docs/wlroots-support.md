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
| Preview dialog | `ok/gui/wlroots/PreviewDialog.py` |

## Connection Lifecycle

Constructing `DeviceManager` does not open a Wayland socket. Device refresh or start
creates the connection lazily through `WaylandConnection.get()`.

Socket discovery scans `$XDG_RUNTIME_DIR/wayland-*`, keeps actual socket files, and
sorts them by descending numeric suffix. The first socket that accepts a connection
and exposes the required protocols is used. If no socket file is found, discovery
falls back to `$WAYLAND_DISPLAY` or `wayland-0`.

`WaylandConnection` is a process-wide singleton shared by capture and interaction.
Its registry binds screencopy, shared memory, seat, output, virtual input, and
foreign-toplevel globals. `connected()` polls the display descriptor for connection
errors. Disconnect resets the singleton and all bound globals.

## Device Model

The Linux desktop appears as one `wayland` device with identifier
`wayland_desktop`. Its resolution comes from the first `wl_output`. A title or app ID
from the first advertised toplevel may be used as the device name; this does not
change the capture target.

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

A capture lock serializes frame requests from the task executor and preview dialog.
This is required because both consumers share one Wayland display connection.

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

## Wayland Preview

The Start tab exposes **Wayland Preview** on Linux. The button is enabled when the
preferred device has type `wayland`.

The dialog:

- validates that the active capture method is a connected `WlrootsCaptureMethod`
- requests frames on a daemon worker thread
- allows only one outstanding preview request
- refreshes once per second
- converts BGR frames to copied RGB `QImage` objects
- preserves aspect ratio and centers the image
- displays capture state and frame dimensions
- stops its timer when closed

The preview is view-only. It does not inject pointer or keyboard input, select an
output, record video, or select a capture region.

## Limits

- Only compositors exposing the required wlroots protocols are supported.
- Capture uses the first output and includes the whole output.
- Multi-output selection is not exposed.
- Socket selection is automatic and has no persisted GUI override.
- Window-level crop, geometry, resize, activation, and foreground control are not available.
- Linux game launch, scheduled tasks, and background audio controls are not available.

## Validation

Use the repository virtual environment:

```bash
./.venv/bin/python -m compileall -q ok
QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m unittest -q \
  tests.test_wlroots_preview \
  tests.test_capture_update
```

Protocol behavior that depends on a real compositor must be verified in the target
wlroots session. Unit tests cover frame conversion, preview state, capture retry,
and capture cleanup behavior.
