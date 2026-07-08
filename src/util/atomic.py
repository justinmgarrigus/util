"""
Various operations that must remain operational even for multiprocessing.
"""

import json
import os
import pathlib
import tempfile
import threading
import time

from typing import Any, List, Optional, Tuple, Union


class AtomicWriteFile:
    """
    Allows atomic writes of a file. This is necessary if it could be dangerous
    for a process to see this file if it were partially-written (e.g., if the
    file is formatted like JSON and the process attempts to read it as valid
    JSON).
    """

    def __init__(
        self: "AtomicWriteFile",
        path: Union[str, pathlib.Path],
        mode: str,
        **kwargs,
    ) -> None:
        assert "w" in mode, f"This can only be used in write mode"

        self.path = pathlib.Path(path)
        self.mode = mode
        self.kwargs = kwargs
        self._tmp = None
        self._tmp_name = None

    def __enter__(self: "AtomicWriteFile"):
        self._tmp = tempfile.NamedTemporaryFile(
            mode=self.mode,
            delete=False,
            dir=self.path.parent,
            **self.kwargs,
        )
        self._tmp_name = self._tmp.name
        return self._tmp

    def __exit__(self: "AtomicWriteFile", exc_type, exc_val, exc_tb):
        try:
            self._tmp.close()
            if exc_type is None:
                # Flush file contents to disk.
                with open(self._tmp_name, "rb") as f:
                    os.fsync(f.fileno())

                # Atomically replace the destination.
                os.replace(self._tmp_name, self.path)

                # Flush the directory entry.
                dir_fd = os.open(self.path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            else:
                # An exception occurred, discard the temporary file.
                if os.path.exists(self._tmp_name):
                    os.unlink(self._tmp_name)
        finally:
            self._tmp = None
            self._tmp_name

        # Propagate any exception.
        return False


class AtomicEdit:
    """
    Allows atomic editing of a file. This is implemented through spinning on a
    shared lock. Each subprocess uses the following syntax:

    ```python
    with AtomicEdit("path/to/file.txt") as f:
        content = f.read_all()
        f.write_all(content + "foo")
    ```

    We offer two operations, "read_all" and "write_all". If a collection of
    subprocesses arrive at this "with" statement at the same time, then exactly
    one succeeds. They gain exclusive access to the file and proceed forward.
    "read_all" reads the entire file contents, and "write_all" writes the entire
    file contents. As soon as that process exits the block, other processes are
    allowed to try for it.
    """

    def __init__(
        self: "AtomicEdit",
        path: str,
        timeout: float = 10.0,
        backoff: bool = True,
    ) -> None:
        """
        A lock is placed at `{path}.lock`. Timeout is a time given in seconds;
        if the lock is acquired and it has not been modified since this many
        seconds, then we assume the lock is stale and we remove it. If backoff
        is set, then each failure to acquire the lock results in more time
        being passed until the next acquire; if it's not set, we only check the
        lock at a constant rate of once every 0.01 seconds.
        """

        self.path = path
        self.lock = f"{path}.lock"
        self.backoff = backoff
        self.is_acquired = False

        # For the timeout, add a tiny bit extra time. For some reason, it
        # appears that the user could receive the file sooner than the timeout,
        # so this is added for consistency sake.
        self.timeout = timeout + 0.01

    def __enter__(self: "AtomicEdit") -> "AtomicEdit":
        assert not self.is_acquired

        def acquire() -> bool:
            # Returns True if we acquired the file, or False otherwise. First
            # determine if we should remove the lock.
            try:
                # Assume the lock exists.
                time_since_modified = time.time() - os.path.getmtime(self.lock)
                assert time_since_modified >= 0
                if time_since_modified > self.timeout:
                    os.rmdir(self.lock)  # Multiple may do concurrently
            except OSError:
                pass  # Maybe lock doesn't exist; this is fine.

            # Actually attempt to acquire the lock now.
            try:
                os.mkdir(self.lock)
                return True
            except FileExistsError:
                return False

        sleep_amount = 0.01
        while not acquire():
            time.sleep(sleep_amount)
            if self.backoff:
                sleep_amount = min(sleep_amount * 2, 1.0)

        # We have exclusive access to the file.
        self.is_acquired = True
        return self

    def __exit__(self: "AtomicEdit", exc_type, exc_val, exc_tb):
        assert os.path.exists(self.lock), self.lock
        assert self.is_acquired
        os.rmdir(self.lock)
        self.is_acquired = False

        # Propagate any exception.
        return False

    def read_all(self: "AtomicEdit") -> str:
        """
        Reads the entire contents of the file. It must be acquired.
        """

        assert self.is_acquired
        with open(self.path, "r") as f:
            return f.read()

    def write_all(self: "AtomicEdit", contents: str) -> None:
        """
        Writes the entire contents of the file. It must be acquired.
        """

        assert self.is_acquired
        with AtomicWriteFile(self.path, "w") as f:
            f.write(contents)


class AtomicQueue:
    """
    An atomic queue implemented via an AtomicEdit object on a dummy file. The
    file stores the state of the queue. This object works even when many
    simultaneous subprocesses attempt to use it at the same time. This queue is
    FIFO; for the initial data of length N provided to it, the first call to
    "pop" will return the 0th index, and the first call to "push" will be the
    Nth item removed.
    """

    def __init__(
        self: "AtomicQueue",
        init_data: Optional[List[Any]] = None,
        path: str = "queue.json",
        timeout: float = 10.0,
    ) -> None:
        """
        Creates a new queue. The path should not be interacted with manually,
        but it should only be used by AtomicQueues with a shared purpose (i.e.,
        don't make it point to a global area that other unrelated AtomicQueues
        may use). The initial data must be JSON-serializable.
        """

        self.file = AtomicEdit(path, timeout=timeout)
        self.pid = os.getpid()
        self.tid = threading.get_ident()

        # Write the contents to the file.
        if init_data is not None:
            self._setup(init_data)

    def _setup(self: "AtomicQueue", content: List[Any]) -> None:
        """
        Sets up the file with the initial data.
        """

        assert isinstance(content, list)
        data = {"pid": self.pid, "tid": self.tid, "data": content}
        s = json.dumps(data)

        if self.file.is_acquired:  # It may be acquired by us.
            self.file.write_all(s)
        else:
            with self.file:
                self.file.write_all(s)

    def pop(self: "AtomicQueue", backoff: bool = True) -> Any:
        """
        Returns a single item from the queue and updates it to remove that item.
        This operation blocks until data becomes available; if no data is
        available at the time of being called, it spins.
        """

        def try_pop() -> Tuple[bool, Any]:
            # Tries to get data from the file; on success, return (True, data),
            # otherwise return (False, None).
            with self.file:
                if not os.path.exists(self.file.path):
                    return (False, None)

                content = self.file.read_all()
                obj = json.loads(content)
                assert all(k in obj.keys() for k in ("pid", "tid", "data"))
                assert isinstance(obj["data"], list)
                if len(obj["data"]) > 0:
                    item = obj["data"].pop(0)
                    self.file.write_all(json.dumps(obj))
                    return (True, item)
                else:
                    return (False, None)

        sleep_amount = 0.01
        success, data = try_pop()
        while not success:
            time.sleep(sleep_amount)
            if backoff:
                sleep_amount = min(sleep_amount * 2, 1.0)
            success, data = try_pop()

        return data

    def push(self: "AtomicQueue", item: Any) -> None:
        """
        Puts a single item into the queue and updates it.
        """

        with self.file:
            # Does the file exist?
            if not os.path.exists(self.file.path):
                # It doesn't exist. This is special behavior; if we want to
                # push to an empty file, interpret the file as containing an
                # empty list. The next parts should succeed.
                self._setup([])

            content = self.file.read_all()
            obj = json.loads(content)
            assert all(k in obj.keys() for k in ("pid", "tid", "data"))
            assert isinstance(obj["data"], list)
            obj["data"].append(item)
            self.file.write_all(json.dumps(obj))

    def __len__(self: "AtomicQueue") -> int:
        """
        Returns the length of the queue.
        """

        with self.file:
            content = self.file.read_all()
            obj = json.loads(content)
            assert all(k in obj.keys() for k in ("pid", "tid", "data"))
            assert isinstance(obj["data"], list)
            return len(obj["data"])

    def delete(self: "AtomicQueue", force=False) -> None:
        """
        This object uses a metadata file, so this function removes that file.
        If "force" is not set, then *only* the process/thread which created this
        queue is allowed to delete it; if "force" is set, then anyone can remove
        it.
        """

        # Check if the file wasn't already deleted.
        if os.path.exists(self.file.path):
            with self.file:
                content = self.file.read_all()
                obj = json.loads(content)
                assert all(k in obj.keys() for k in ("pid", "tid", "data"))

                if force or (
                    os.getpid() == obj["pid"]
                    and threading.get_ident() == obj["tid"]
                ):
                    os.remove(self.file.path)
