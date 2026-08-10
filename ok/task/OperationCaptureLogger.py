import json
import os
import re
import shutil
import threading
import time
from datetime import datetime

import cv2

from ok.feature.Box import Box
from ok.task.exceptions import FinishedException, TaskDisabledException
from ok.util.GlobalConfig import basic_options
from ok.util.file import get_relative_path
from ok.util.logger import Logger


logger = Logger.get_logger(__name__)


class OperationCaptureLogger:
    def __init__(self, executor):
        self.executor = executor
        self.lock = threading.Lock()
        self.session_dir = None
        self.jsonl_path = None
        self.sequence = 0
        self.retention_checked = False

    def log(self, operation, success=True, before_frame=None, after_delay=None, success_kind=None,
            capture_before=True, capture_after=True, **metadata):
        if not self.enabled():
            return
        try:
            config = self._config()
            if after_delay is None:
                after_delay = config.get('Operation Capture Log After Delay', 0.2)
            if before_frame is None and capture_before:
                before_frame = self._copy_frame(self.executor.nullable_frame())
            after_frame = None
            if capture_after and after_delay > 0:
                self.executor.sleep(after_delay)
            if capture_after:
                after_frame = self._copy_frame(self.executor.next_frame(time_out=2))
            self._write(operation, bool(success), before_frame, after_frame, metadata,
                        success_kind=success_kind)
        except (TaskDisabledException, FinishedException):
            raise
        except Exception as e:
            logger.debug(f'operation capture log failed: {e}')

    def log_event(self, operation, success=True, success_kind=None, **metadata):
        self.log(operation, success=success, success_kind=success_kind, capture_before=False,
                 capture_after=False, **metadata)

    def capture_frame(self):
        if not self.enabled():
            return None
        return self._copy_frame(self.executor.nullable_frame())

    def enabled(self):
        try:
            return bool(self._config().get('Enable Operation Capture Log', False))
        except Exception:
            return False

    def _config(self):
        return self.executor.global_config.get_config(basic_options)

    def _write(self, operation, success, before_frame, after_frame, metadata, success_kind=None):
        with self.lock:
            self._ensure_session()
            self.sequence += 1
            timestamp = datetime.now().astimezone().isoformat(timespec='milliseconds')
            prefix = f'{self.sequence:06d}_{self._safe_name(operation)}'
            before_name = f'{prefix}_before.png' if before_frame is not None else None
            after_name = f'{prefix}_after.png' if after_frame is not None else None
            if before_name:
                cv2.imwrite(os.path.join(self.session_dir, before_name), before_frame)
            if after_name:
                cv2.imwrite(os.path.join(self.session_dir, after_name), after_frame)
            record = {
                'sequence': self.sequence,
                'time': timestamp,
                'timestamp': timestamp,
                'task': self._task_name(),
                'operation': operation,
                'success': success,
                'success_kind': success_kind,
                'before': before_name,
                'after': after_name,
                'args': self._jsonable(metadata),
                'metadata': self._jsonable(metadata),
            }
            with open(self.jsonl_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _ensure_session(self):
        if self.session_dir:
            return
        root = self._root_dir()
        os.makedirs(root, exist_ok=True)
        if not self.retention_checked:
            self._prune_old_sessions(root)
            self.retention_checked = True
        task_name = self._safe_name(self._task_name())
        name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_name}"
        self.session_dir = os.path.join(root, name)
        index = 1
        while os.path.exists(self.session_dir):
            self.session_dir = os.path.join(root, f'{name}_{index}')
            index += 1
        os.makedirs(self.session_dir, exist_ok=True)
        self.jsonl_path = os.path.join(self.session_dir, 'operation.jsonl')

    def _root_dir(self):
        folder = self._config().get('Operation Capture Log Folder', 'operation_logs')
        if not folder:
            folder = 'operation_logs'
        if os.path.isabs(folder):
            return folder
        return get_relative_path(folder)

    def _prune_old_sessions(self, root):
        days = self._config().get('Operation Capture Log Retention Days', 7)
        if days <= 0:
            return
        cutoff = time.time() - days * 86400
        try:
            for name in os.listdir(root):
                path = os.path.join(root, name)
                if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
        except Exception as e:
            logger.warning(f'operation capture retention failed: {e}')

    @staticmethod
    def _copy_frame(frame):
        if frame is None:
            return None
        return frame.copy()

    @staticmethod
    def _safe_name(value):
        return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(value)).strip('_') or 'operation'

    def _task_name(self):
        task = getattr(self.executor, 'current_task', None)
        if task is None:
            return None
        return getattr(task, 'name', None) or task.__class__.__name__

    @classmethod
    def _jsonable(cls, value):
        if isinstance(value, Box):
            return {
                'name': value.name,
                'x': value.x,
                'y': value.y,
                'width': value.width,
                'height': value.height,
                'confidence': value.confidence,
            }
        if isinstance(value, dict):
            return {str(k): cls._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._jsonable(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
