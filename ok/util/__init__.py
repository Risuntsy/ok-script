import sys

if sys.platform == 'win32':
    from ok.util.gpu_driver_settings import is_gpu_post_processing_enabled
else:
    def is_gpu_post_processing_enabled():
        return False
