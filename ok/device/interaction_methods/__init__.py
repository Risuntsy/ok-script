from ok.device.interaction_methods.adb import ADBInteraction
from ok.device.interaction_methods.base import BaseInteraction
from ok.device.interaction_methods.browser import BrowserInteraction
from ok.device.interaction_methods.do_nothing import DoNothingInteraction
import sys

if sys.platform == "win32":
    from ok.device.interaction_methods.foreground_post_message import ForegroundPostMessageInteraction
    from ok.device.interaction_methods.genshin import GenshinInteraction, INPUT, MOUSEINPUT, SendInput
    from ok.device.interaction_methods.post_message import PostMessageInteraction
    from ok.device.interaction_methods.pydirect import PyDirectInteraction
    from ok.device.interaction_methods.pynput import PynputInteraction
    from ok.device.interaction_methods.win_keys import PYDIRECT_KEY_MAP, normalize_pydirect_key, vk_key_dict
else:
    ForegroundPostMessageInteraction = GenshinInteraction = PostMessageInteraction = PyDirectInteraction = PynputInteraction = PYDIRECT_KEY_MAP = normalize_pydirect_key = vk_key_dict = None
from ok.device.interaction_methods.keys import ADB_KEY_MAP
from ok.device.interaction_methods.swipe import insert_swipe

if sys.platform == "linux":
    from ok.device.interaction_methods.wlroots import WlrootsInteraction
else:
    WlrootsInteraction = None
