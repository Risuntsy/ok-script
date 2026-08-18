import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import ok.device.DeviceManager as device_manager_module
from ok.device.DeviceManager import DeviceManager
from ok.device.capture_methods.wlroots import WlrootsCaptureMethod
from ok.device.wlroots.connection import WaylandConnection
from ok.util.wayland import is_wuwa_title, select_preferred_socket


class FakeCapture:
    def __init__(self, hwnd=None, socket_name=None):
        self.socket_name = socket_name
        self.exit_event = None
        self.closed = False

    def start_or_stop(self):
        return True

    def connected(self):
        return not self.closed

    def close(self):
        self.closed = True


class FakeInteraction:
    def __init__(self, capture=None, hwnd_window=None):
        self.capture = capture
        self.destroyed = False

    def on_destroy(self):
        self.destroyed = True


class TestWaylandSocketSelection(unittest.TestCase):
    def test_list_supported_sockets_returns_every_compatible_socket(self):
        def connect(connection, socket_name):
            if socket_name == 'wayland-1':
                raise RuntimeError('missing screencopy')
            size = 1000 + int(socket_name.rsplit('-', 1)[1])
            connection.outputs = [SimpleNamespace(width=size, height=700)]
            connection.toplevels = [SimpleNamespace(title=f'Desktop {socket_name}', app_id='')]

        with patch.object(WaylandConnection, 'list_available_sockets',
                          return_value=['wayland-2', 'wayland-1', 'wayland-0']), \
                patch.object(WaylandConnection, 'connect', autospec=True, side_effect=connect), \
                patch.object(WaylandConnection, 'disconnect', autospec=True):
            sockets = WaylandConnection.list_supported_sockets()

        self.assertEqual(['wayland-2', 'wayland-0'], [item['socket_name'] for item in sockets])
        self.assertEqual('Desktop wayland-2', sockets[0]['nick'])
        self.assertEqual(1002, sockets[0]['width'])

    def test_device_refresh_exposes_each_supported_socket(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager.device_dict = {
            'pc': {'device': 'windows'},
            'wayland_old': {'device': 'wayland'},
        }
        supported = [
            {'socket_name': 'wayland-2', 'nick': 'Nested', 'width': 1920, 'height': 1080},
            {'socket_name': 'wayland-0', 'nick': 'Host', 'width': 2560, 'height': 1440},
        ]

        with patch.object(WaylandConnection, 'list_supported_sockets', return_value=supported):
            manager.update_wlroots_device()

        self.assertNotIn('wayland_old', manager.device_dict)
        self.assertIn('pc', manager.device_dict)
        self.assertEqual('wayland-2', manager.device_dict['wayland_wayland-2']['socket'])
        self.assertEqual('Nested (wayland-2)', manager.device_dict['wayland_wayland-2']['nick'])
        self.assertEqual('2560x1440', manager.device_dict['wayland_wayland-0']['resolution'])

    def test_selected_socket_recreates_capture_and_interaction(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager.exit_event = threading.Event()
        manager.device_dict = {
            'wayland_wayland-2': {
                'imei': 'wayland_wayland-2', 'device': 'wayland',
                'socket': 'wayland-2', 'connected': True,
            },
            'wayland_wayland-0': {
                'imei': 'wayland_wayland-0', 'device': 'wayland',
                'socket': 'wayland-0', 'connected': True,
            },
        }
        manager.config = {'preferred': 'wayland_wayland-2'}
        manager.capture_method = None
        manager.interaction = None
        manager.win_interaction_class = FakeInteraction

        with patch.object(device_manager_module, 'WlrootsCaptureMethod', FakeCapture):
            manager.do_start()
            first_capture = manager.capture_method
            first_interaction = manager.interaction
            self.assertEqual('wayland-2', first_capture.socket_name)

            manager.config['preferred'] = 'wayland_wayland-0'
            manager.do_start()

        self.assertTrue(first_capture.closed)
        self.assertTrue(first_interaction.destroyed)
        self.assertEqual('wayland-0', manager.capture_method.socket_name)
        self.assertIs(manager.capture_method, manager.interaction.capture)

    def test_is_wuwa_title_matches_expected_variants(self):
        for title in ('Wuthering Waves', '鸣潮', 'Wuwa', 'Wu Wa', 'Wu wa', 'wuthering  waves - v2.1'):
            self.assertTrue(is_wuwa_title(title), title)
        for title in ('', 'Firefox', 'Steam', 'Wu'):
            self.assertFalse(is_wuwa_title(title), title)

    def test_select_preferred_socket_prefers_wuwa_title_with_biggest_id(self):
        supported = [
            {'socket_name': 'wayland-1', 'titles': ['Wuthering Waves']},
            {'socket_name': 'wayland-3', 'titles': ['Some Other App']},
            {'socket_name': 'wayland-4', 'titles': ['鸣潮']},
        ]
        self.assertEqual('wayland-4', select_preferred_socket(supported))

    def test_select_preferred_socket_falls_back_to_max_socket_id(self):
        supported = [
            {'socket_name': 'wayland-1', 'titles': ['Firefox']},
            {'socket_name': 'wayland-3', 'titles': []},
            {'socket_name': 'wayland-2', 'titles': ['Steam']},
        ]
        self.assertEqual('wayland-3', select_preferred_socket(supported))

    def test_update_wlroots_device_auto_selects_wuwa_socket(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager.device_dict = {}
        manager.config = {'preferred': ''}
        supported = [
            {'socket_name': 'wayland-3', 'nick': 'Desktop', 'width': 1920, 'height': 1080, 'titles': []},
            {'socket_name': 'wayland-1', 'nick': 'Wuthering Waves', 'width': 2560, 'height': 1440,
             'titles': ['Wuthering Waves']},
        ]

        with patch.object(WaylandConnection, 'list_supported_sockets', return_value=supported):
            manager.update_wlroots_device()

        self.assertEqual('wayland_wayland-1', manager.config['preferred'])

    def test_update_wlroots_device_keeps_existing_valid_preference(self):
        manager = DeviceManager.__new__(DeviceManager)
        manager.device_dict = {}
        manager.config = {'preferred': 'wayland_wayland-3'}
        supported = [
            {'socket_name': 'wayland-3', 'nick': 'Desktop', 'width': 1920, 'height': 1080, 'titles': []},
            {'socket_name': 'wayland-1', 'nick': 'Wuthering Waves', 'width': 2560, 'height': 1440,
             'titles': ['Wuthering Waves']},
        ]

        with patch.object(WaylandConnection, 'list_supported_sockets', return_value=supported):
            manager.update_wlroots_device()

        self.assertEqual('wayland_wayland-3', manager.config['preferred'])

    def test_capture_connects_to_explicit_socket(self):
        connection = SimpleNamespace(socket_name='wayland-3', connected=lambda: True)
        capture = WlrootsCaptureMethod(socket_name='wayland-3')

        with patch.object(WaylandConnection, 'get', return_value=connection) as get_connection:
            self.assertTrue(capture.start_or_stop())

        get_connection.assert_called_once_with('wayland-3')


if __name__ == '__main__':
    unittest.main()
