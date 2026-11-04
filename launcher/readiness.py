"""Wait for an HTTP server to come up.

Used to hold off starting the UI until the API answers, and to hold off
opening a browser/Electron window until Vite is actually serving — otherwise
the window opens onto a connection-refused page.
"""

from __future__ import annotations

import http.client
import time
import urllib.request
from collections.abc import Callable


def is_serving(url: str, timeout: float = 2.0) -> bool:
    """True if a GET to `url` returns HTTP 200 right now; False on any other
    status or on any connection error (refused, reset, timed out, ...)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (OSError, http.client.HTTPException):
        # OSError covers URLError, refused/reset connections, and timeouts;
        # HTTPException covers a server that's up but not yet speaking HTTP properly.
        return False


def wait_until_serving(
    url: str,
    timeout: float,
    should_abort: Callable[[], bool] | None = None,
    interval: float = 0.3,
) -> bool:
    """Poll `url` until it serves 200 (→ True) or `timeout` seconds pass (→ False).

    `should_abort` is checked before every attempt; returning True gives up
    immediately — e.g. "the process we're waiting on has already crashed",
    so there's no point sitting out the rest of the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if should_abort is not None and should_abort():
            return False
        if is_serving(url):
            return True
        time.sleep(interval)
    return False
