import asyncio
import errno
import os
import sys
from hashlib import sha256
from tempfile import gettempdir
from time import time
from typing import Any, Self, cast

import portalocker


class ALockError(Exception):
  pass


class ALock:
  """An asynchronous context manager creating a system-wide lock."""

  def __init__(
    self,
    name: str,
    timeout: float = 10e8,
    check_interval: float = 0.25,
    reentrant: bool = False,
    lock_directory: str | None = None,
  ) -> None:
    """Create a new `ALock` context manager.

    Parameters
    ----------
    name:
      The name of the lock. Must be unique across locks.
    timeout:
      The maximum time in seconds to wait for the lock to be acquired. Optional, defaults to 10e8 seconds.
    check_interval:
      The interval in seconds between lock attempts. Optional, defaults 0.25 seconds.
    reentrant:
      Indicated whether the lock should be reentrant. Optional, defaults to `False`.
    lock_directory:
      The directory to store the lock file. Optional, defaults to the system's temporary directory.
    """
    self._timeout = timeout
    self._check_interval = check_interval

    lock_directory = gettempdir() if lock_directory is None else lock_directory
    unique_token = sha256(name.encode()).hexdigest()

    self._filepath = os.path.join(lock_directory, "alock-" + unique_token + ".lock")
    self._reentrant = reentrant
    self._enter_count = 0

  async def __aenter__(self) -> Self:
    """Acquire the lock.

    Returns
    -------
    The lock object.
    """
    if self._enter_count > 0:
      if self._reentrant:
        self._enter_count += 1
        return self

      raise ALockError("Trying re-enter a non-reentrant lock")

    current_time = call_time = time()
    while call_time + self._timeout >= current_time:
      self._lockfile = open(self._filepath, "w")  # noqa

      try:
        portalocker.lock(
          self._lockfile,
          cast(portalocker.constants.LockFlags, portalocker.constants.LOCK_NB | portalocker.constants.LOCK_EX),
        )
        self._enter_count = 1
      except portalocker.exceptions.LockException:
        pass
      else:
        return self

      current_time = time()
      check_interval = self._check_interval if self._timeout > self._check_interval else self._timeout

      await asyncio.sleep(check_interval)

    raise ALockError("Timeout was reached")

  async def __aexit__(self, *exc: Any) -> None:
    """Release the lock.

    Parameters
    ----------
    exc:
      The exception details.
    """
    self._enter_count -= 1

    if self._enter_count > 0:
      return

    if sys.platform.startswith("linux"):
      # In Linux you can delete a locked file
      os.unlink(self._filepath)

    self._lockfile.close()

    if sys.platform == "win32":
      # In Windows you need to unlock a file before deletion
      try:
        os.remove(self._filepath)
      except OSError as e:
        # Mute exception in case an access was already acquired (EACCES) and in the rarer case when it was already
        # released and the file was deleted (ENOENT)
        if e.errno not in [errno.EACCES, errno.ENOENT]:
          raise
