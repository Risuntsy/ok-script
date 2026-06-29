# Wayland wlroots 支持现状

> 复核日期：2026-06-14
> 范围：ok-script
> 目标：Windows + Linux(wlroots) 多平台支持，不用 Linux 路径替换 Windows 路径。

## 当前结论

ok-script 已有并行 Linux wlroots 路径。Windows 继续使用原有 Win32 capture/interaction/window 管理能力；Linux wlroots 使用 Wayland socket、screencopy、virtual pointer、virtual keyboard 实现基础自动化。

当前 Linux 支持是 wlroots-only，适用于 labwc、Sway、Hyprland、River、Wayfire 等 compositor。不支持 GNOME Mutter、KDE KWin、portal、PipeWire 或 D-Bus 捕获路径。

## 当前架构

```text
DeviceManager
  ├─ device type: "windows" → HwndWindow + Windows capture/interaction
  ├─ device type: "wayland" → WlrootsCaptureMethod + WlrootsInteraction
  ├─ device type: "browser" → BrowserCaptureMethod + BrowserInteraction
  └─ device type: "adb"     → ADBCaptureMethod + ADBInteraction
```

## Linux wlroots 实现

| 组件 | 当前实现 |
|---|---|
| Socket discovery | `ok/util/wayland.py::discover_sockets()` |
| Wayland registry | `ok/device/wlroots/connection.py::WaylandConnection` |
| Capture | `ok/device/capture_methods/wlroots.py::WlrootsCaptureMethod` |
| Interaction | `ok/device/interaction_methods/wlroots.py::WlrootsInteraction` |
| Key mapping | `ok/device/interaction_methods/evdev_keys.py` |
| Protocol bindings | `ok/device/wlroots/protocols/` |

## Wayland 连接规则

- `DeviceManager.__init__` 不打开 Wayland socket。
- Refresh/Start 阶段才调用 `WaylandConnection.get()`。
- 自动扫描 `$XDG_RUNTIME_DIR/wayland-*`，按编号从高到低尝试连接，优先 nested session。
- 当前没有 GUI socket 下拉选择，也没有 persisted manual override。
- 当前强制要求 `zwlr_screencopy_manager_v1`、`wl_shm`、`wl_seat`。
- `zwlr_virtual_pointer_manager_v1`、`zwp_virtual_keyboard_manager_v1`、`zwlr_foreign_toplevel_manager_v1` 会在存在时绑定；完整输入自动化依赖 virtual pointer/keyboard。

## Capture 行为

- 当前捕获第一个 `wl_output`。
- 当前捕获整个 output，不做窗口级裁剪。
- 当前不实现 `WaylandWindow`、窗口几何、`capture_output_region` 或 compositor IPC crop。

## Interaction 行为

- 鼠标通过 `zwlr_virtual_pointer_manager_v1` 注入。
- 键盘通过 `zwp_virtual_keyboard_manager_v1` 注入。
- `WlrootsInteraction.on_destroy()` 会释放 pointer、keyboard 和 keymap fd。

## Shutdown 行为

- GUI 关闭、托盘退出、`communicate.quit` 均应走统一 `App.quit()`。
- `App.quit()` 设置 `exit_event`，销毁 executor，停止 screenshot 队列，关闭 device capture/interaction/HwndWindow，隐藏 tray，并退出 Qt event loop。
- `ExitEvent.set()` 是幂等的，避免重复 shutdown 时反复 stop handler。

## 依赖声明

跨平台依赖必须使用 platform marker：

```python
install_requires=[
    'pywin32>=306; sys_platform == "win32"',
    'pydirectinput==1.0.4; sys_platform == "win32"',
    'pycaw==20240210; sys_platform == "win32"',
    'pywayland>=0.4.18; sys_platform == "linux"',
]
```

## 已完成

- Linux `wayland` device branch。
- output-level wlroots screencopy。
- virtual pointer / virtual keyboard input。
- Linux 下不创建 `HwndWindow` 常规路径。
- Linux 下不启动 `update_window_size` 线程。
- Windows-only GUI 和系统功能按平台隐藏或跳过。
- Wayland socket lazy connection。
- 跨平台条件依赖声明。
- GUI graceful shutdown 统一路径。

## 未完成

- 真实游戏 wlroots 会话测试。
- 自动化集成测试：click、type、scroll、swipe。
- 多显示器 output 选择。
- Wayland socket GUI 下拉选择与持久化。
- 窗口级裁剪、窗口几何、bring_to_front。
- Linux 游戏启动和计划任务替代实现。
