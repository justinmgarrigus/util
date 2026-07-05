"""
Functions that can't be categorized in other ways. 
"""

import os
import pathlib 
import tempfile

from typing import Union


def raise_expr(exception):
    """
    Allows us to raise an exception as an expression, for things like list 
    comprehensions or inline if-else expressions which don't allow us to raise
    since it's a statement.  
    """

    raise exception 


class AtomicFile:
    """
    Allows atomic writes of a file. This is necessary if it could be dangerous 
    for a process to see this file if it were partially-written (e.g., if the 
    file is formatted like JSON and the process attempts to read it as valid 
    JSON).
    """
    
    def __init__(
        self: "AtomicFile", 
        path: Union[str, pathlib.Path], 
        mode: str, **kwargs
    ) -> None:
        self.path = pathlib.Path(path)
        self.mode = mode
        self.kwargs = kwargs
        self._tmp = None
        self._tmp_name = None


    def __enter__(self: "AtomicFile"):
        if "r" in self.mode:
            self._tmp = open(self.path, self.mode, **self.kwargs)
            return self._tmp 
        else:
            self._tmp = tempfile.NamedTemporaryFile(
                mode=self.mode, 
                delete=False, 
                dir=self.path.parent, 
                **self.kwargs
            )
            self._tmp_name = self._tmp.name 
            return self._tmp


    def __exit__(self: "AtomicFile", exc_type, exc_val, exc_tb):
        try:
            self._tmp.close()
            if "r" in self.mode:
                # In reading mode, we don't actually do anything special here.
                # File reads are functionally fine.
                pass 
            else:
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
