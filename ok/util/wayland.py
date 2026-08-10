import os, re, glob, stat as _stat, sys

def is_wayland() -> bool:
    """True if running under any Wayland compositor."""
    return sys.platform == 'linux' and bool(os.environ.get('WAYLAND_DISPLAY'))

def is_wlroots() -> bool:
    """
    Best-effort heuristic: checks XDG_CURRENT_DESKTOP for known wlroots compositor
    names. Final verification is the registry probe in WaylandConnection._check_required.
    """
    if not is_wayland():
        return False
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    return any(d in desktop for d in ('sway', 'hyprland', 'labwc', 'river',
                                       'wayfire', 'wlroots', 'dwl'))

def discover_sockets() -> list[str]:
    """
    Scan $XDG_RUNTIME_DIR for all Wayland sockets (wayland-N files),
    return them sorted by descending numeric suffix.

    Highest number = innermost nested compositor — try it first.
    Falls back to [$WAYLAND_DISPLAY or 'wayland-0'] if no sockets found on disk.

    Example results on a doubly-nested session:
        ['wayland-2', 'wayland-1', 'wayland-0']
    """
    runtime = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    pattern = os.path.join(runtime, 'wayland-*')
    paths = glob.glob(pattern)
    # Keep only real sockets (skip .lock files and non-socket entries)
    sockets = [
        os.path.basename(p)
        for p in paths
        if not p.endswith('.lock')
        and os.path.exists(p)
        and _stat.S_ISSOCK(os.stat(p).st_mode)
    ]
    def _num(name: str) -> int:
        m = re.search(r'(\d+)$', name)
        return int(m.group(1)) if m else -1
    sockets.sort(key=_num, reverse=True)
    if not sockets:
        fallback = os.environ.get('WAYLAND_DISPLAY', 'wayland-0')
        sockets = [fallback]
    return sockets

def wayland_socket_path(name: str | None = None) -> str:
    """Full filesystem path for a given Wayland socket name (or the best auto-detected one)."""
    runtime = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    if name is None:
        name = discover_sockets()[0]
    return os.path.join(runtime, name)

def compositor_name() -> str:
    return os.environ.get('XDG_CURRENT_DESKTOP', 'unknown')
