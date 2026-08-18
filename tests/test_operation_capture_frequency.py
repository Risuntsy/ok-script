import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ok.task.task import ExecutorOperation


class TestOperationCaptureFrequency(unittest.TestCase):
    def make_operation(self):
        executor = SimpleNamespace(
            scene=None,
            interaction=Mock(),
            reset_scene=Mock(),
        )
        operation = ExecutorOperation(executor, None)
        operation.operation_capture_logger = Mock()
        return operation, executor

    def test_click_records_metadata_without_copying_frames(self):
        operation, executor = self.make_operation()

        self.assertTrue(operation.click(100, 200, name='target'))

        operation.operation_capture_logger.capture_frame.assert_not_called()
        operation.operation_capture_logger.log.assert_not_called()
        operation.operation_capture_logger.log_event.assert_called_once_with(
            'click', success=True, success_kind='sent', x=100, y=200, key='left',
            name='target', move_back=False, move=True, down_time=0.02, after_sleep=0)
        executor.interaction.click.assert_called_once()

    def test_send_key_records_metadata_without_copying_frames(self):
        operation, executor = self.make_operation()

        self.assertTrue(operation.send_key('f'))

        operation.operation_capture_logger.capture_frame.assert_not_called()
        operation.operation_capture_logger.log.assert_not_called()
        operation.operation_capture_logger.log_event.assert_called_once_with(
            'send_key', success=True, success_kind='sent', key='f', down_time=0.02,
            after_sleep=0)
        executor.interaction.send_key.assert_called_once_with('f', 0.02)


if __name__ == '__main__':
    unittest.main()
