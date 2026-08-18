import os
import sys
import setuptools

os.environ["PYTHONIOENCODING"] = "utf-8"

# PEP 517 in-process builds exec() this file's source without adding its own
# directory to sys.path, so the sibling get_pypi_latest_version module below
# would otherwise fail to import.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VERSION_NUM = os.environ.get('OK_SCRIPT_BUILD_VERSION')
if VERSION_NUM:
    print(f'building explicit version {VERSION_NUM}')
else:
    from get_pypi_latest_version import GetPyPiLatestVersion

    obtainer = GetPyPiLatestVersion()
    latest_version = obtainer("ok-script")
    VERSION_NUM = obtainer.version_add_one(latest_version, add_patch=True)
    print(f'latest_version is {latest_version} new version is {VERSION_NUM}')

setuptools.setup(version=VERSION_NUM)
