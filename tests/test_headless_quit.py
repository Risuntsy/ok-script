import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

import ok.task.TaskExecutor as task_executor_module
from ok.core.events import communicate
from ok.task.TaskExecutor import TaskExecutor


class FakeTask:
    name = "FakeTask"
    exit_after_task = True
    config = {}

    def __init__(self):
        self._enabled = True
        self.running = False
        self.start_time = None
        self._app = SimpleNamespace(tr=lambda message: message)

    @property
    def enabled(self):
        return self._enabled

    def run(self):
        pass

    def disable(self):
        self._enabled = False

    def info_set(self, *_args):
        pass

    def on_destroy(self):
        pass


class FailingFakeTask(FakeTask):
    def run(self):
        raise RuntimeError("fake task failed")


class TestHeadlessQuit(unittest.TestCase):
    def setUp(self):
        if QCoreApplication.instance() is not None:
            self.skipTest("headless quit tests require no active Qt application")

    @unittest.skip("2.0 EventBus delivers quit immediately; Qt queued-signal behavior does not apply")
    def test_plain_quit_signal_from_worker_is_not_delivered_without_event_loop(self):
        called = threading.Event()

        def on_quit():
            called.set()

        communicate.quit.connect(on_quit)
        try:
            thread = threading.Thread(target=communicate.quit.emit)
            thread.start()
            thread.join(timeout=1)

            self.assertFalse(called.wait(timeout=0.1))
        finally:
            communicate.quit.disconnect(on_quit)

    def test_emit_quit_sets_exit_event_without_qt_event_loop(self):
        exit_event = threading.Event()

        delivered_to_qt = communicate.emit_quit(exit_event)

        self.assertFalse(delivered_to_qt)
        self.assertTrue(exit_event.is_set())

    def test_exit_after_task_sets_exit_event_in_headless_executor(self):
        exit_event = threading.Event()
        task = FakeTask()
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.exit_event = exit_event
        executor.paused = False
        executor._frame = None
        executor._last_frame_time = 0
        executor.current_task = None
        executor.trigger_tasks = []
        executor.onetime_tasks = [task]
        executor.device_manager = Mock()
        executor.device_manager.stop_hwnd = Mock()
        executor.device_manager.interaction = None
        executor.destroy = Mock()
        executor.next_task = Mock(side_effect=[(task, False, False), (None, False, False)])
        executor.next_frame = Mock(return_value=object())
        executor.reset_scene = Mock()

        with patch.object(task_executor_module.time, 'sleep'):
            executor.execute()

        self.assertTrue(exit_event.is_set())
        executor.device_manager.stop_hwnd.assert_called_once()
        executor.destroy.assert_called_once()

    def test_exit_after_failed_task_sets_exit_event_in_headless_executor(self):
        exit_event = threading.Event()
        task = FailingFakeTask()
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.exit_event = exit_event
        executor.paused = False
        executor._frame = None
        executor._last_frame_time = 0
        executor.current_task = None
        executor.trigger_tasks = []
        executor.onetime_tasks = [task]
        executor.device_manager = Mock()
        executor.device_manager.stop_hwnd = Mock()
        executor.device_manager.interaction = None
        executor.destroy = Mock()
        executor.next_task = Mock(side_effect=[(task, False, False), (None, False, False)])
        executor.next_frame = Mock(return_value=object())
        executor.reset_scene = Mock()

        executor.execute()

        self.assertTrue(exit_event.is_set())
        executor.device_manager.stop_hwnd.assert_not_called()
        executor.destroy.assert_called_once()


if __name__ == '__main__':
    unittest.main()
