import time

import requests
from packaging.version import Version


class GetPyPiLatestVersion:
    def __call__(self, module_name, retries=5, timeout=30):
        url = f"https://pypi.org/pypi/{module_name}/json"
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                return response.json()["info"]["version"]
            except (requests.exceptions.SSLError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as exc:
                last_error = exc
                if attempt == retries:
                    break
                # Transient TLS/EOF/network blips during editable builds.
                time.sleep(min(2 ** (attempt - 1), 8))
        raise last_error

    def version_add_one(self, version, add_patch=False):
        parsed = Version(version)
        major = parsed.major
        minor = parsed.minor
        micro = parsed.micro + 1 if add_patch else parsed.micro
        if not add_patch:
            minor += 1
            micro = 0
        return f"{major}.{minor}.{micro}"
