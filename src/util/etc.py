"""
Functions that can't be categorized in other ways.
"""


def raise_expr(exception):
    """
    Allows us to raise an exception as an expression, for things like list
    comprehensions or inline if-else expressions which don't allow us to raise
    since it's a statement.
    """

    raise exception
