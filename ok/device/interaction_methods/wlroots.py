import mmap
import os
import time
from .base import BaseInteraction
from ok.util.logger import Logger
from ok.device.wlroots.connection import WaylandConnection

logger = Logger.get_logger(__name__)

_BUTTON_CODES = {
    'left': 272,
    'right': 273,
    'middle': 274,
}

_MIN_DOWN_TIME = 0.03

class WlrootsInteraction(BaseInteraction):
    name = "Wlroots Interaction"

    def __init__(self, capture=None, hwnd_window=None):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self.connection = None
        self._pointer = None
        self._keyboard = None
        self._keymap_fd = -1
        self._keymap_size = 0
        self._init()

    def _init(self):
        try:
            self.connection = WaylandConnection.get()

            # Virtual pointer
            if self.connection.vp_manager and self.connection.seat:
                self._pointer = self.connection.vp_manager.create_virtual_pointer(
                    self.connection.seat
                )

            # Virtual keyboard
            if self.connection.vk_manager and self.connection.seat:
                self._keyboard = self.connection.vk_manager.create_virtual_keyboard(
                    self.connection.seat
                )
                self._init_keymap()

            logger.info(f'WlrootsInteraction initialized pointer={self._pointer is not None} keyboard={self._keyboard is not None}')
        except Exception as e:
            logger.error(f'WlrootsInteraction init failed: {e}')

    def clickable(self):
        return True

    def _init_keymap(self):
        # Self-contained qwerty keymap. Virtual-keyboard events send evdev
        # keycodes; XKB keycodes are evdev + 8, so keep these values aligned.
        keymap_data = (
            b'xkb_keymap {\n'
            b' xkb_keycodes "ok" {\n'
            b'  minimum = 8; maximum = 255;\n'
            b'  <ESC> = 9; <AE01> = 10; <AE02> = 11; <AE03> = 12; <AE04> = 13;\n'
            b'  <AE05> = 14; <AE06> = 15; <AE07> = 16; <AE08> = 17; <AE09> = 18; <AE10> = 19;\n'
            b'  <BKSP> = 22; <TAB> = 23; <AD01> = 24; <AD02> = 25; <AD03> = 26; <AD04> = 27;\n'
            b'  <AD05> = 28; <AD06> = 29; <AD07> = 30; <AD08> = 31; <AD09> = 32; <AD10> = 33;\n'
            b'  <RTRN> = 36; <LCTL> = 37; <AC01> = 38; <AC02> = 39; <AC03> = 40; <AC04> = 41;\n'
            b'  <AC05> = 42; <AC06> = 43; <AC07> = 44; <AC08> = 45; <AC09> = 46; <TLDE> = 49;\n'
            b'  <LFSH> = 50; <AB01> = 52; <AB02> = 53; <AB03> = 54; <AB04> = 55; <AB05> = 56;\n'
            b'  <AB06> = 57; <AB07> = 58; <AB08> = 59; <AB09> = 60; <AB10> = 61; <RTSH> = 62;\n'
            b'  <LALT> = 64; <SPCE> = 65; <CAPS> = 66;\n'
            b'  <FK01> = 67; <FK02> = 68; <FK03> = 69; <FK04> = 70; <FK05> = 71; <FK06> = 72;\n'
            b'  <FK07> = 73; <FK08> = 74; <FK09> = 75; <FK10> = 76; <FK11> = 95; <FK12> = 96;\n'
            b'  <RCTL> = 105; <RALT> = 108; <HOME> = 110; <UP> = 111; <PGUP> = 112;\n'
            b'  <LEFT> = 113; <RGHT> = 114; <END> = 115; <DOWN> = 116; <PGDN> = 117;\n'
            b'  <INS> = 118; <DELE> = 119; <LWIN> = 133; <RWIN> = 134;\n'
            b' };\n'
            b' xkb_types "min" { type "ONE_LEVEL" { modifiers = none; map[none] = 1; level_name[1] = "Any"; }; };\n'
            b' xkb_compat "min" { };\n'
            b' xkb_symbols "ok" {\n'
            b'  key <ESC> { [ Escape ] }; key <AE01> { [ 1 ] }; key <AE02> { [ 2 ] }; key <AE03> { [ 3 ] };\n'
            b'  key <AE04> { [ 4 ] }; key <AE05> { [ 5 ] }; key <AE06> { [ 6 ] }; key <AE07> { [ 7 ] };\n'
            b'  key <AE08> { [ 8 ] }; key <AE09> { [ 9 ] }; key <AE10> { [ 0 ] }; key <BKSP> { [ BackSpace ] };\n'
            b'  key <TAB> { [ Tab ] }; key <AD01> { [ q ] }; key <AD02> { [ w ] }; key <AD03> { [ e ] };\n'
            b'  key <AD04> { [ r ] }; key <AD05> { [ t ] }; key <AD06> { [ y ] }; key <AD07> { [ u ] };\n'
            b'  key <AD08> { [ i ] }; key <AD09> { [ o ] }; key <AD10> { [ p ] }; key <RTRN> { [ Return ] };\n'
            b'  key <LCTL> { [ Control_L ] }; key <AC01> { [ a ] }; key <AC02> { [ s ] }; key <AC03> { [ d ] };\n'
            b'  key <AC04> { [ f ] }; key <AC05> { [ g ] }; key <AC06> { [ h ] }; key <AC07> { [ j ] };\n'
            b'  key <AC08> { [ k ] }; key <AC09> { [ l ] }; key <TLDE> { [ grave ] }; key <LFSH> { [ Shift_L ] };\n'
            b'  key <AB01> { [ z ] }; key <AB02> { [ x ] }; key <AB03> { [ c ] }; key <AB04> { [ v ] };\n'
            b'  key <AB05> { [ b ] }; key <AB06> { [ n ] }; key <AB07> { [ m ] }; key <AB08> { [ comma ] };\n'
            b'  key <AB09> { [ period ] }; key <AB10> { [ slash ] }; key <RTSH> { [ Shift_R ] };\n'
            b'  key <LALT> { [ Alt_L ] }; key <SPCE> { [ space ] }; key <CAPS> { [ Caps_Lock ] };\n'
            b'  key <FK01> { [ F1 ] }; key <FK02> { [ F2 ] }; key <FK03> { [ F3 ] }; key <FK04> { [ F4 ] };\n'
            b'  key <FK05> { [ F5 ] }; key <FK06> { [ F6 ] }; key <FK07> { [ F7 ] }; key <FK08> { [ F8 ] };\n'
            b'  key <FK09> { [ F9 ] }; key <FK10> { [ F10 ] }; key <FK11> { [ F11 ] }; key <FK12> { [ F12 ] };\n'
            b'  key <RCTL> { [ Control_R ] }; key <RALT> { [ Alt_R ] }; key <HOME> { [ Home ] }; key <UP> { [ Up ] };\n'
            b'  key <PGUP> { [ Prior ] }; key <LEFT> { [ Left ] }; key <RGHT> { [ Right ] }; key <END> { [ End ] };\n'
            b'  key <DOWN> { [ Down ] }; key <PGDN> { [ Next ] }; key <INS> { [ Insert ] }; key <DELE> { [ Delete ] };\n'
            b'  key <LWIN> { [ Super_L ] }; key <RWIN> { [ Super_R ] };\n'
            b'  modifier_map Shift { <LFSH>, <RTSH> }; modifier_map Control { <LCTL>, <RCTL> };\n'
            b'  modifier_map Mod1 { <LALT>, <RALT> }; modifier_map Mod4 { <LWIN>, <RWIN> };\n'
            b' };\n'
            b' xkb_geometry "min" { description = "Minimal"; width = 18; height = 5; };\n'
            b'};\n'
            b'\x00'
        )
        self._keymap_size = len(keymap_data)

        try:
            fd = os.memfd_create("keymap", os.MFD_CLOEXEC)
        except AttributeError:
            import tempfile
            fd, path = tempfile.mkstemp(dir='/dev/shm', prefix='ok-keymap-')
            os.unlink(path)

        os.ftruncate(fd, self._keymap_size)
        mm = mmap.mmap(fd, self._keymap_size, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.write(keymap_data)
        mm.close()

        # 1 = WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1
        self._keyboard.keymap(1, fd, self._keymap_size)
        self._keymap_fd = fd

    def close(self):
        if self._pointer:
            self._pointer.destroy()
            self._pointer = None
        if self._keyboard:
            self._keyboard.destroy()
            self._keyboard = None
        if self._keymap_fd != -1:
            os.close(self._keymap_fd)
            self._keymap_fd = -1

    def on_destroy(self):
        self.close()

    def move_to(self, x, y):
        if self._pointer:
            # Use actual capture dimensions instead of 0xffffffff
            width = 1280
            height = 720
            if self.capture and hasattr(self.capture, '_width') and hasattr(self.capture, '_height'):
                w = self.capture._width
                h = self.capture._height
                if w > 0 and h > 0:
                    width = w
                    height = h
            wl_time = self._wl_time()
            self._pointer.motion_absolute(wl_time, int(x), int(y), width, height)
            self._pointer.frame()
            self.connection.dispatch()

    def left_click(self):
        self._click_button(272)

    def right_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02):
        self.click(x, y, move_back=move_back, name=name, down_time=down_time, key="right")

    def left_down(self):
        if self._pointer:
            self._pointer.button(0, 272, 1) # Pressed
            self._pointer.frame()
            self.connection.dispatch()

    def left_up(self):
        if self._pointer:
            self._pointer.button(0, 272, 0) # Released
            self._pointer.frame()
            self.connection.dispatch()

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        if x != -1 and y != -1:
            abs_x, abs_y = self.capture.get_abs_cords(x, y) if self.capture else (x, y)
            self.move_to(abs_x, abs_y)
            time.sleep(0.02)
        btn_code = self._button_code(key)
        if self._pointer:
            wl_time = self._wl_time()
            self._pointer.button(wl_time, btn_code, 1) # Pressed
            self._pointer.frame()
            self.connection.dispatch()

    def mouse_up(self, key="left"):
        btn_code = self._button_code(key)
        if self._pointer:
            wl_time = self._wl_time()
            self._pointer.button(wl_time, btn_code, 0) # Released
            self._pointer.frame()
            self.connection.dispatch()

    def _button_code(self, key):
        return _BUTTON_CODES.get(key, _BUTTON_CODES['left'])

    def _down_time(self, down_time):
        try:
            return max(float(down_time), _MIN_DOWN_TIME)
        except (TypeError, ValueError):
            return _MIN_DOWN_TIME

    def _click_button(self, btn_code, down_time=0.05):
        if self._pointer:
            wl_time = self._wl_time()
            self._pointer.button(wl_time, btn_code, 1) # Pressed
            self._pointer.frame()
            self.connection.dispatch()
            time.sleep(self._down_time(down_time))
            wl_time = self._wl_time()
            self._pointer.button(wl_time, btn_code, 0) # Released
            self._pointer.frame()
            self.connection.dispatch()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=False, key="left"):
        current_pos = None
        if move_back and self._pointer:
            current_pos = (self._pointer.x, self._pointer.y) if hasattr(self._pointer, 'x') else None

        if x != -1 and y != -1:
            abs_x, abs_y = self.capture.get_abs_cords(x, y) if self.capture else (x, y)
            self.move_to(abs_x, abs_y)
            time.sleep(0.02)

        self._click_button(self._button_code(key), down_time=down_time)

        if current_pos:
            time.sleep(0.05)
            self.move_to(*current_pos)

    def swipe(self, x1, y1, x2, y2, duration=0.5):
        from ok.device.interaction_methods.swipe import insert_swipe
        insert_swipe(self, x1, y1, x2, y2, duration)

    def scroll(self, x, y, scroll_amount):
        if self._pointer:
            # Move to position first
            if x != -1 and y != -1:
                abs_x, abs_y = self.capture.get_abs_cords(x, y) if self.capture else (x, y)
                self.move_to(abs_x, abs_y)
                time.sleep(0.02)
            # libinput uses 10 or 15 for a "click" or wheel detent
            value = 15 if scroll_amount > 0 else -15
            for _ in range(abs(scroll_amount)):
                wl_time = self._wl_time()
                # 0 = WL_POINTER_AXIS_VERTICAL
                self._pointer.axis(wl_time, 0, value * 256) # wl_fixed
                self._pointer.frame()
                self.connection.dispatch()
                time.sleep(0.02)

    def _wl_time(self):
        import time
        return int(time.monotonic() * 1000)

    def send_key(self, key, down_time=0.05):
        if not self._keyboard:
            return

        from ok.device.interaction_methods.evdev_keys import get_evdev_keycode
        keycode = get_evdev_keycode(key)
        if keycode is not None:
            wl_time = self._wl_time()
            self._keyboard.key(wl_time, keycode, 1) # pressed
            self.connection.dispatch()
            time.sleep(self._down_time(down_time))
            wl_time = self._wl_time()
            self._keyboard.key(wl_time, keycode, 0) # released
            self.connection.dispatch()
        else:
            logger.error(f"Failed to resolve evdev keycode for key: {key}")

    def key_down(self, key):
        if not self._keyboard:
            return

        from ok.device.interaction_methods.evdev_keys import get_evdev_keycode
        keycode = get_evdev_keycode(key)
        if keycode is not None:
            wl_time = self._wl_time()
            self._keyboard.key(wl_time, keycode, 1) # pressed
            self.connection.dispatch()
        else:
            logger.error(f"Failed to resolve evdev keycode for key: {key}")

    def send_key_down(self, key):
        self.key_down(key)

    def key_up(self, key):
        if not self._keyboard:
            return

        from ok.device.interaction_methods.evdev_keys import get_evdev_keycode
        keycode = get_evdev_keycode(key)
        if keycode is not None:
            wl_time = self._wl_time()
            self._keyboard.key(wl_time, keycode, 0) # released
            self.connection.dispatch()
        else:
            logger.error(f"Failed to resolve evdev keycode for key: {key}")

    def send_key_up(self, key):
        self.key_up(key)
