"""
Functions that can't be categorized in other ways.
"""

from typing import Any


def raise_expr(exception):
    """
    Allows us to raise an exception as an expression, for things like list
    comprehensions or inline if-else expressions which don't allow us to raise
    since it's a statement.
    """

    raise exception


class Stub:
    """
    A stub is an object which can represent the presence of something, but
    shouldn't represent any functionality.
    """

    def _fail(self, action: str) -> None:
        raise RuntimeError(
            f"This is a Stub object; we cannot perform the action [{action}]."
        )

    def __init__(self: "Stub", **kwargs) -> None:
        """
        Creates a stub. Each keyword argument can be accessed like normal, but
        anything besides those keyword arguments raise errors.
        """

        self.__dict__.update(kwargs)

    def __getattr__(self: "Stub", name: str) -> Any:
        self._fail(f"getattr({name})")

    def __call__(self: "Stub", *args, **kwargs) -> None:
        self._fail("call")

    def __getitem__(self: "Stub", key: str) -> None:
        self._fail(f"getitem({key})")

    def __setitem__(self: "Stub", key: str, value: Any) -> None:
        self._fail(f"setitem({key})")

    def __iter__(self: "Stub") -> None:
        self._fail("iter")

    def __len__(self: "Stub") -> None:
        self._fail("len")

    def __bool__(self: "Stub") -> bool:
        """
        Returns False. This allows us to test for stub-ness.
        """

        return False

    def __repr__(self: "Stub") -> None:
        s = ", ".join(f"{key}: {value}" for key, value in self.attrs.items())
        return "<Stub: {s}>"
