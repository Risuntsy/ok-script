"""Whether the running PyAppify install can answer update queries.

`pyappify.get_version_list` is always importable, but it only works when the
app was started by a PyAppify launcher: the launcher exports
`PYAPPIFY_VERSION`, and without it the call raises instead of returning
versions. Running from source (a plain `python main.py`, which is the normal
Linux setup) leaves it unset, so the update controls must stay disabled rather
than fail every check.
"""

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

# Launchers below this version have no version-list API.
MINIMUM_UPDATE_CHECK_VERSION = (1, 2, 2)


def parse_pyappify_version(version):
    """Return the version as a tuple, or None when it is unset or malformed."""
    if not isinstance(version, str) or not version:
        return None
    normalized = version[1:] if version.startswith('v') else version
    parts = normalized.split('.')
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def supports_update_check(pyappify_module):
    """Return whether update controls can be offered for this pyappify module."""
    if not callable(getattr(pyappify_module, 'get_version_list', None)):
        return False
    if not hasattr(pyappify_module, 'pyappify_version'):
        # A module that does not describe its launcher at all (a test double)
        # keeps the previous behaviour of trusting get_version_list.
        return True
    version = parse_pyappify_version(pyappify_module.pyappify_version)
    if version is None or version < MINIMUM_UPDATE_CHECK_VERSION:
        logger.info(
            'update controls disabled: pyappify_version='
            f'{pyappify_module.pyappify_version!r} cannot serve version lists')
        return False
    return True
