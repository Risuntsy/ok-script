import sys

def get_default_capture_methods():
    if sys.platform == "linux":
        return ['Wlroots']
    elif sys.platform == "win32":
        return ['WGC', 'BitBlt', 'ForegroundBitBlt', 'DXGI']
    return []
