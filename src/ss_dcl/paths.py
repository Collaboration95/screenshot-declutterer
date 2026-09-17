"""Runtime location of the app's own state and cache directories.

Everything the app writes on its own behalf (state, memory, settings, logs,
thumbnails, LiteRT pid/log) lives under a single runtime root derived here.
By default that root is the user's home directory, so nothing changes for
normal use.

Setting SS_DCL_HOME relocates the whole runtime tree to an isolated directory.
That is what the demo fixture / documentation capture tooling uses: pointing
SS_DCL_HOME at a throwaway directory (paired with SS_DCL_DESKTOP) means
documentation runs never touch real user state and never need to repurpose HOME.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Environment variable that relocates the runtime root (state + cache).
ENV_RUNTIME_HOME = "SS_DCL_HOME"

#: Directory name of the state folder created under the runtime root.
STATE_DIR_NAME = ".ss-dcl"

#: Cache folder name created under the runtime root.
CACHE_DIR_NAME = "ss-dcl"


def runtime_home() -> Path:
    """Return the runtime root: SS_DCL_HOME when set, otherwise HOME."""
    raw = os.environ.get(ENV_RUNTIME_HOME)
    if raw and raw.strip():
        return Path(raw).expanduser()
    return Path.home()


def state_dir() -> Path:
    """Return the directory holding state/memory/settings/log files."""
    return runtime_home() / STATE_DIR_NAME


def cache_dir() -> Path:
    """Return the directory holding derived caches (thumbnails)."""
    return runtime_home() / ".cache" / CACHE_DIR_NAME
