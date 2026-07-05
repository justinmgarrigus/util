"""
Obtaining secret information.
"""

import os
import stat
import yaml

from util.git import get_git_root


def get():
    """
    Reads all secrets. These are stored in a file either at the root of the
    current Git repository or in the `UTIL_SECRETS_PATH` environment variable.
    """

    path = os.environ.get("UTIL_SECRETS_PATH", f"{get_git_root()}/secrets.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f'No secrets.yaml file was provided at "{path}".'
        )

    # Ensure the file has the correct permissions.
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077 != 0:
        raise PermissionError(
            (
                f'Secrets file "{path}" is unsafe and accessible by '
                f"group/others ({oct(mode)})"
            )
        )

    # Read the data.
    with open(path, "r") as f:
        props = yaml.safe_load(f)
        assert isinstance(props, dict)

    # The secrets file must not contain bash expressions, it should just be
    # strings. If the user included something literal like "$WORK" in there,
    # then raise an error.
    assert all("$" not in val for val in props.values())
    return props
