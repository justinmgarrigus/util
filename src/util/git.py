import os


def get_git_root(start_path: str = ".") -> str: 
    """
    Returns the path of the directory (parent of start_path) which contains 
    .git in it. If no git root exists, raises a FileNotFoundError. 
    """

    cwd = os.path.abspath(start_path)
    while True:
        if os.path.exists(f"{cwd}/.git"):
            return cwd 

        parent = os.path.dirname(cwd)
        if cwd == parent:
            raise FileNotFoundError(f"No .git found from {start_path}")
        
        cwd = parent 
