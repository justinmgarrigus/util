"""
Various operations that must remain operational even for multiprocessing.
"""

import os
import pathlib
import tempfile

from typing import Union


class AtomicWriteFile:
    """
    Allows atomic writes of a file. This is necessary if it could be dangerous
    for a process to see this file if it were partially-written (e.g., if the
    file is formatted like JSON and the process attempts to read it as valid
    JSON).
    """

    def __init__(
        self: "AtomicFile", path: Union[str, pathlib.Path], mode: str, **kwargs
    ) -> None:
        assert "w" in mode, f"This can only be used in write mode"

        self.path = pathlib.Path(path)
        self.mode = mode
        self.kwargs = kwargs
        self._tmp = None
        self._tmp_name = None

    def __enter__(self: "AtomicFile"):
        self._tmp = tempfile.NamedTemporaryFile(
            mode=self.mode,
            delete=False,
            dir=self.path.parent,
            **self.kwargs,
        )
        self._tmp_name = self._tmp.name
        return self._tmp

    def __exit__(self: "AtomicFile", exc_type, exc_val, exc_tb):
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

    def __init__(self: "AtomicEdit", path: str) -> None:
        """
        Creates the file, but does not open it yet. A lock is placed at
        `{path}.lock`.
        """

        self.path = path
        self.lock = f"{path}.lock"
        self.is_acquired = False

    def __enter__(self: "AtomicEdit") -> "AtomicEdit":
        def acquire() -> bool:
            """
            Returns True if we acquired the file, or False otherwise.
            """
            try:
                os.mkdir(self.lock)
                return True
            except FileExistsError:
                return False

        sleep_amount = 0.01
        while not acquire():
            time.sleep(sleep_amount)
            sleep_amount = min(sleep_amount * 2, 1.0)

        # We have exclusive access to the file.
        self.is_acquired = True
        return self

    def __exit__(self: "AtomicEdit", exc_type, exc_val, exc_tb):
        assert os.path.exists(self.lock), self.lock
        os.remove(self.lock)
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
        with open(self.path, "w") as f:
            f.write(contents)
