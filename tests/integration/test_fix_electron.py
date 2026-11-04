"""scripts/fix_electron.sh repairs an Electron install that npm left broken.

Electron's postinstall unzips its binary in the background; on Node 26 the
event loop drains mid-unzip, the process exits 0, and no path.txt is written —
so `electron` fails with "Electron failed to install correctly".
"""

from __future__ import annotations

import json
import subprocess
import zipfile

import pytest

from launcher.paths import REPO_ROOT

pytestmark = pytest.mark.integration

SCRIPT = REPO_ROOT / "scripts" / "fix_electron.sh"
BINARY = "Electron.app/Contents/MacOS/Electron"


@pytest.fixture()
def broken_install(tmp_path):
    pkg = tmp_path / "node_modules" / "electron"
    (pkg / "dist" / "Electron.app").mkdir(parents=True)  # a half-extracted dist
    (pkg / "package.json").write_text(json.dumps({"name": "electron", "version": "1.2.3"}))
    cache = tmp_path / "cache" / "somehash"
    cache.mkdir(parents=True)
    with zipfile.ZipFile(cache / "electron-v1.2.3-darwin-arm64.zip", "w") as z:
        z.writestr(BINARY, "#!/bin/sh\necho v1.2.3\n")
        z.writestr("version", "1.2.3")
    return pkg, tmp_path / "cache"


def _run(pkg, cache):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin", "ELECTRON_DIR": str(pkg), "ELECTRON_CACHE_DIR": str(cache), "ELECTRON_ARCH": "arm64"}
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)


def test_repairs_from_the_cached_zip(broken_install):
    pkg, cache = broken_install
    result = _run(pkg, cache)
    assert result.returncode == 0, result.stderr
    assert (pkg / "path.txt").read_text() == BINARY
    assert (pkg / "dist" / BINARY).is_file()
    assert (pkg / "dist" / "version").read_text() == "1.2.3"


def test_leaves_a_working_install_alone(broken_install):
    pkg, cache = broken_install
    _run(pkg, cache)
    marker = pkg / "dist" / "untouched"
    marker.write_text("")
    result = _run(pkg, cache)
    assert result.returncode == 0
    assert marker.exists()
    assert "already installed" in result.stdout
