class TaskDisabledException(BaseException):
    pass


class CannotFindException(Exception):
    pass


class FinishedException(BaseException):
    pass


class WaitFailedException(Exception):
    pass


class CaptureException(Exception):
    pass


class HotkeyConfigException(Exception):
    def __init__(self, key):
        self.key = key
        super().__init__(f"{key} is invalid, please check the hotkey config!")
