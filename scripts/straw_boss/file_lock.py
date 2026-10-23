"""Blocking exclusive locks released when their owning file is closed."""
from __future__ import annotations

import errno
import os
import time
from typing import IO


def lock_exclusive(file: IO) -> None:
    if os.name != 'nt':
        import fcntl

        fcntl.flock(file, fcntl.LOCK_EX)
        return

    import msvcrt

    # Lock the same byte even for an empty or append-mode lock file. Windows
    # permits locking beyond EOF; closing the descriptor releases the region.
    file.seek(0)
    while True:
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EDEADLK, errno.EAGAIN}:
                raise
            time.sleep(0.05)
