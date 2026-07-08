from typing import Callable
from util.etc import raise_expr, Stub


def test_raise_expr() -> None:
    """
    raise_expr allows raising an exception within an expression.
    """

    try:
        x = raise_expr(FileNotFoundError())
        assert False
    except FileNotFoundError:
        pass

    xs = [2, 4, 6, 8, 10, 12, 13, 14, 16]
    try:
        ys = [xx if xx % 2 == 0 else raise_expr(FileNotFoundError) for xx in xs]
        assert False
    except FileNotFoundError:
        pass


def test_stub_access() -> None:
    """
    Accessing variables should fail.
    """

    s1 = Stub()
    try:
        x = s1.foo
        raise ValueError()
    except RuntimeError:
        pass

    s2 = Stub(foo="bar")
    x = s2.foo
    try:
        y = s2.bar
        raise ValueError()
    except RuntimeError:
        pass

    s3 = Stub()
    s3.foo = "bar"
    x = s3.foo


def test_stub_no_functionality():
    """
    Stubs don't have a lot of existing functionality.
    """

    def test(action: Callable) -> None:
        try:
            action()
            raise ValueError()
        except RuntimeError:
            pass

    s = Stub()

    # __call__
    try:
        s()
        raise ValueError()
    except RuntimeError:
        pass

    # __getitem__
    try:
        x = s[0]
        raise ValueError()
    except RuntimeError:
        pass

    # __setitem__
    try:
        s[0] = "foo"
        raise ValueError()
    except RuntimeError:
        pass

    # __iter__
    try:
        for _ in s:
            pass
        raise ValueError()
    except RuntimeError:
        pass

    # __len__
    try:
        x = len(s)
        raise ValueError()
    except RuntimeError:
        pass


def test_stub_bool():
    """
    Stubs should be treated as False, so users can test for stub-ness.
    """

    assert bool(Stub()) is False
    if Stub():
        raise ValueError()
