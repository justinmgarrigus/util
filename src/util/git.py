from git import Repo
from pathlib import Path
from typing import Dict


def get_git_root(child_path: str = ".") -> str:
    """
    Returns the path of the directory (parent of child_path) which contains
    .git in it.
    """

    repo = Repo(child_path, search_parent_directories=True)
    return repo.working_tree_dir


def get_git_properties() -> Dict[str, str]:
    """
    Returns a collection of properties about the current git repository,
    including:
      - "project_name" (str): name of the project.
      - "commit_hash" (str): hash of the current commit.
      - "branch" (str): name of the current branch if the current
        branch is not detached, else "detached".
      - "commit_message" (str): message associated with the last commit on this
        branch.
    """

    repo = Repo(".", search_parent_directories=True)
    return {
        "project_name": Path(repo.working_tree_dir).name,
        "commit_hash": repo.head.commit.hexsha,
        "branch": (
            repo.active_branch.name if not repo.head.is_detached else "detached"
        ),
        "commit_message": repo.head.commit.message.strip(),
    }
