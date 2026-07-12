# Headless Shutdown

## Contract

GUI and headless applications use the same shared `exit_event`, but they request
shutdown through different delivery mechanisms.

- With a Qt application instance, `communicate.emit_quit()` emits the Qt `quit`
  signal so shutdown runs through the GUI application lifecycle.
- Without a Qt application instance, `communicate.emit_quit(exit_event)` sets the
  exit event directly and returns `False`.

This distinction is required because headless mode does not run a Qt event loop and
cannot deliver a queued cross-thread signal.

## Call Sites

`TaskExecutor.execute()` uses `emit_quit(self.exit_event)` when a completed one-time
task has `exit_after_task` enabled.

`HwndWindow.update_window_size()` uses the same helper when the configured Windows
application should exit after the game window closes.

`OK.wait_task()` also sets the exit event while completing headless task waiting and
cleanup.

## Shutdown Behavior

Setting `exit_event` is idempotent. Handlers, task sleeps, capture polling, frame
requests, and executor loops check the event and stop their work. Device teardown
then closes capture resources, interaction resources, window monitoring, screenshot
workers, and application services.

Wayland capture polls in short intervals and checks `exit_event`, allowing shutdown
to interrupt a frame request before the shared display connection is disconnected.

## Validation

Run the platform-compatible regression tests with the repository virtual environment:

```bash
./.venv/bin/python -m unittest -q \
  tests.test_headless_quit \
  tests.test_task_executor_queue
```

The tests cover direct headless event delivery, one-time-task exit behavior, and task
queue execution without requiring a real game process.
