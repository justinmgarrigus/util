"""
System of registering and archiving research artifacts. All experiments and
artifacts are logged to the environment variable/secrets property
RESEARCH_PATH.
"""

import datetime
import fcntl
import json
import os
import pathlib
import re
import shutil

from typing import Any, Dict, List, Optional, Union
from util.etc import AtomicFile
from util.git import get_git_properties
from util.secrets import get as get_secrets


class Experiment:
    """
    An Experiment is a group of research artifacts. Each artifact within the
    experiment should have the same queryable structure.
    """

    @staticmethod
    def timestamp(inp: Optional[str] = None) -> Union[str, datetime.datetime]:
        """
        If an input timestamp is provided, then converts it to a datetime
        object. If no input timestamp is provided, then returns the current
        time as a string.
        """

        fmt = "%m/%d/%Y @ %H:%M:%S"  # 07/01/2026 @ 15:30:00
        if inp is None:
            return datetime.datetime.now().strftime(fmt)
        else:
            return datetime.datetime.strptime(inp, fmt)

    @classmethod
    def _get_basedir(cls) -> str:
        # The user may update the base directory multiple times in a single
        # session.
        basedir = os.environ.get("RESEARCH_PATH", None)
        if basedir is None:
            try:
                basedir = get_secrets().get("RESEARCH_PATH", None)
            except:
                basedir = None 

            if basedir is None:
                raise ValueError(
                    (
                        "Error: no RESEARCH_PATH is provided as an environment "
                        "variable or in secrets."
                    )
                )

        if not os.path.exists(basedir):
            os.makedirs(basedir, exist_ok=True)
        return os.path.abspath(basedir)

    @classmethod
    def list(cls) -> List["Experiment"]:
        """
        Lists all experiments (equvalent to the experiment index). The index
        keeps track of all experiments. This loads the index and additionally
        checks it's valid. If the index does not previously exist, then it
        creates an index file. This function is **not cached**, it completely
        regenerates objects each time it's called.
        """

        basedir = cls._get_basedir()
        assert os.path.exists(basedir), basedir

        index_path = f"{basedir}/index.json"
        if not os.path.exists(index_path):
            with AtomicFile(index_path, "w") as f:
                f.write("[]")
        with AtomicFile(index_path, "r") as f:
            index_json = json.load(f)

        # Convert JSON to Experiment objects.
        index = [cls(**exp) for exp in index_json]
        return index

    @classmethod
    def _save_index(cls, index: List[Dict[str, str]]) -> None:
        """
        Updates and saves the index file with the new experiments. After
        creating any Experiment objects, this must be run. (It can be run
        multiple times.)
        """

        basedir = cls._get_basedir()
        index_path = f"{basedir}/index.json"
        assert os.path.exists(index_path), index_path  # Created with list()

        # Serialize the index.
        index_json = [
            {
                "name": exp.name,
                "ident": exp.ident,
                "description": exp.description,
                "created_timestamp": exp.created_timestamp,
                "modified_timestamp": exp.modified_timestamp,
                "project_name": exp.project_name,
                "commit_hash": exp.commit_hash,
                "branch": exp.branch,
                "commit_message": exp.commit_message,
            }
            for exp in index
        ]

        with AtomicFile(index_path, "w") as f:
            json.dump(index_json, f)

    def __init__(
        self: "Experiment",
        name: str,
        ident: str,
        description: str,
        created_timestamp: Optional[str] = None,
        modified_timestamp: Optional[str] = None,
        project_name: Optional[str] = None,
        commit_hash: Optional[str] = None,
        branch: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> None:
        """
        Creates an experiment. "name" and "description" are human-readable,
        while "ident" is unique. If there is one experiment in storage, and the
        user attempts to create a new experiment with the same identifier but a
        different Git commit hash, then this will result in two separate
        experiments since it's not unlikely the artifacts come from different
        distributions. If any of the project parameters are None, then they all
        must be None; this signals that we should obtain them from the current
        repository instead of loaded as arguments.

        This does not save the experiment to disk.
        """

        project_params = (project_name, commit_hash, branch, commit_message)
        if any(p is None for p in project_params):
            assert all(p is None for p in project_params)

            # Obtain the other info needed for logging experiments.
            props = get_git_properties()
            project_name = props["project_name"]
            commit_hash = props["commit_hash"]
            branch = props["branch"]
            commit_message = props["commit_message"]

        # Validate properties.
        assert len(ident) > 0
        assert re.fullmatch(r"^[a-zA-Z0-9\-_\.]+$", ident), (
            f'The identifier "{ident}" contains illegal characters'
        )
        assert len(commit_hash) == 40 and (
            re.fullmatch("^[a-fA-F0-9]+$", commit_hash)
        ), f'The commit hash "{commit_hash}" is not a valid hash'

        self.name = name
        self.ident = ident
        self.description = description
        self.created_timestamp = created_timestamp
        self.modified_timestamp = modified_timestamp
        self.project_name = project_name
        self.commit_hash = commit_hash
        self.branch = branch
        self.commit_message = commit_message

    @property
    def artifacts(self: "Experiment") -> List["Artifact"]:
        """
        Returns the list of Artifacts for this Experiment. This is a function
        instead of a standard property because initially, only the *index* is
        loaded for an Experiment if we do "list()". We don't actually want to
        load the artifacts until the user wants to do something with them.
        """

        git_hash = self.commit_hash[:8]
        path = (
            f"{Experiment._get_basedir()}/exp-{self.ident}-{git_hash}/"
            "index.json"
        )
        if os.path.exists(path):
            with AtomicFile(path, "r") as f:
                data = json.load(f)
            assert all(
                key in data.keys() for key in ("experiment-ident", "artifacts")
            )
            assert data["experiment-ident"] == self.ident

            return [Artifact.from_json(art, self) for art in data["artifacts"]]
        else:
            return []

    def _save(
        self: "Experiment", artifact: Optional["Artifact"] = None
    ) -> None:
        """
        Saves an experiment to disk. Verifies all the parameters, too. Note
        this should *not* be called outside of this file (but it can be called
        via test-cases to confirm Experiment-saving in isolation). The intended
        route is for the user to call "add_artifact" which implicitly re-saves
        this to disk. If an artifact is provided as an argument, then appends
        it to the collection; otherwise, just saves the index.
        """

        # Obtain the contents of the index file.
        index = Experiment.list()

        # Does an experiment exist in our log that contains the same git hash
        # and identifier?
        matching = [
            exp
            for exp in index
            if exp.ident == self.ident and exp.commit_hash == self.commit_hash
        ]
        assert len(matching) <= 1, repr(matching)
        if len(matching) == 1:
            old_exp = matching[0]

            # The experiment exists and is the same experiment, so it's fine to
            # add new artifacts to it. If the name/description are different,
            # just overwrite them. (Note if the commit_hash is the same---which
            # we just confirmed it is---then that implies the project_name,
            # branch, and commit_message should also be the same.)
            assert self.project_name == old_exp.project_name
            assert self.branch == old_exp.branch
            assert self.commit_message == old_exp.commit_message

            # Overwrite the existing experiment.
            old_exp.name = self.name
            old_exp.ident = self.ident
            old_exp.description = self.description
            old_exp.modified_timestamp = Experiment.timestamp()

            # For the current object which the user has access to through
            # "self", update properties to reflect the old object.
            self.created_timestamp = old_exp.created_timestamp
            self.modified_timestamp = old_exp.modified_timestamp

        else:
            # This experiment is being created for the first time.
            self.created_timestamp = Experiment.timestamp()
            self.modified_timestamp = Experiment.timestamp()
            index.append(self)

        # Update the general index. The index contains metadata about each
        # artifact, but not the artifacts themselves.
        Experiment._save_index(index)

        # Update the experiment-specific index.
        git_hash = self.commit_hash[:8]
        dname = f"{Experiment._get_basedir()}/exp-{self.ident}-{git_hash}"
        os.makedirs(dname, exist_ok=True)
        artifacts = self.artifacts
        if artifact is not None:
            assert artifact not in artifacts

            # Before adding the artifact, it must contain the same schema as
            # the others. Compare it with the first artifact. "Schema" refers
            # to the queryable keys in each dictionary; the values must also
            # be the same type (or None).
            def compare(obj1: Any, obj2: Any) -> None:
                assert obj1 is None or obj2 is None or type(obj1) is type(obj2)
                if isinstance(obj1, dict) and isinstance(obj2, dict):
                    assert set(obj1.keys()) == set(obj2.keys())
                    for key in obj1.keys():
                        compare(obj1[key], obj2[key])

            if len(artifacts) > 0:
                compare(artifact.props, artifacts[0].props)

            # Their structure matches, so add the new artifact.
            artifacts.append(artifact)

        experiment_data = {
            "experiment-ident": self.ident,
            "artifacts": [
                artifact.to_json(obj_save_dir=dname, do_copy=True)
                for artifact in artifacts
            ],
        }
        index_path = f"{dname}/index.json"
        with AtomicFile(index_path, "w") as f:
            json.dump(experiment_data, f)

    def add_artifact(self: "Experiment", artifact: "Artifact") -> None:
        """
        Adds an artifact to our storage. Raises an error if this artifact
        already exists. If the artifact does not have an experiment attached to
        it (which may be the case if the artifact was constructed manually),
        then add us as the owner.

        Additions of artifacts (and the subsequent modifications of the
        underlying files) are atomic. Multiple processes can add artifacts at
        the same time without worrying about file state being stale.
        """

        with open(f"{self._get_basedir()}/.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)

            if artifact.experiment is None:
                artifact.experiment = self
            else:
                assert artifact.experiment == self
            assert not artifact.exists()
            self._save(artifact)

    def exists(self: "Experiment", artifact_ident: str) -> bool:
        """
        Returns True if we contain the given artifact identifier, False
        otherwise. This can be used to determine if an artifact already exists
        without actually creating the artifact object.
        """

        return any(artifact_ident == art.ident for art in self.artifacts)

    def __str__(self: "Experiment") -> str:
        return (
            f"Experiment(ident={self.ident}, "
            f"len(artifacts)={len(self.artifacts)})"
        )

    def __repr__(self: "Experiment") -> str:
        return str(self)

    def __eq__(
        self: "Experiment", other: Union["Experiment", Dict, Any]
    ) -> bool:
        """
        Returns True if the other object represents the same kind of Experiment
        as us with the same data. Raises an error if the other experiment is
        unsafe, as we want to discourage the user from doing anything bad.
        """

        if isinstance(other, dict):
            assert all(
                key in other
                for key in (
                    "name",
                    "ident",
                    "description",
                    "created_timestamp",
                    "modified_timestamp",
                    "project_name",
                    "commit_hash",
                    "branch",
                    "commit_message",
                )
            )
            other = Experiment(**other)
        elif not isinstance(other, Experiment):
            return False

        if self.ident == other.ident and self.commit_hash == other.commit_hash:
            # All of our artifacts *must* equal the other. If it doesn't, the
            # user is manually constructing Experiments on their own and is
            # getting themselves in unsafe territory, so raise an error so they
            # can correct their code.
            assert len(self.artifacts) == len(other.artifacts)
            assert all(art in other.artifacts for art in self.artifacts)
            return True
        else:
            return False


class Artifact:
    """
    An Artifact is a single research item, like the result of an experiment.
    Artifacts are queryable and associated with experiments. Artifacts are
    composed of a collection of properties. Artifacts may also contain files,
    which are copied to a different location.
    """

    def __init__(
        self: "Artifact",
        experiment: Experiment,
        ident: str,
        props: Dict[str, Any],
        timestamp: Optional[str] = None,
    ):
        """
        Creates a new artifact. "props" are queryable. All artifacts within the
        same Experiment must contain the same properties. If any of the values
        in this props list represent a file or directory, then they *must* be a
        pathlib.Path object (we raise exceptions for strings that point to a
        file/directory but are not pathlib.Path objects); these will be copied
        into the Artifact destination, and their paths will be changed to
        reflect the fact they're copied.
        """

        # Check if any of the properties are paths.
        for key, value in props.items():
            if isinstance(value, str) and os.path.exists(value):
                raise ValueError(
                    (
                        f'Error: tried to create an artifact "{ident}", but '
                        f'one of the properties (key = "{key}", value = '
                        f'"{value}") is a string and represents a valid path. '
                        "This is ambiguous since we do not know if we should "
                        "copy that path to the destination. To be explicit, "
                        "either implement precautions so it doesn't equal a "
                        "path or turn it into a pathlib.Path object to resolve "
                        "this ambiguity and enable copying."
                    )
                )

        self.experiment = experiment
        self.ident = ident
        self.props = props
        self.timestamp = (
            timestamp if timestamp is not None else Experiment.timestamp()
        )

    def exists(self: "Artifact") -> bool:
        """
        Returns True if this artifact exists in the index, or False otherwise.
        This can be used to determine if we can skip an artifact-collection due
        to it already being collected.
        """

        return self.experiment.exists(self.ident)

    @classmethod
    def from_json(
        cls, obj: Dict[str, Any], experiment: Optional[Experiment] = None
    ) -> "Artifact":
        """
        Returns an Artifact object created from a JSON representation.
        """

        assert all(
            key in obj.keys()
            for key in ("artifact-ident", "timestamp", "properties")
        )

        # When we load the JSON properties, auto-cast any strings which are
        # paths into pathlib.Path objects.
        def deserialize(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: deserialize(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [deserialize(o) for o in obj]
            else:
                assert obj is None or isinstance(obj, (int, str, float))
                if isinstance(obj, str) and os.path.exists(obj):
                    return pathlib.Path(obj)
                else:
                    return obj

        return Artifact(
            experiment=experiment,
            ident=obj["artifact-ident"],
            props=deserialize(obj["properties"]),
            timestamp=obj["timestamp"],
        )

    def to_json(
        self: "Artifact", do_copy: bool, obj_save_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Turns us into a JSON representation. For any pathlib.Path object,
        change its location so its pointed to obj_save_dir instead. If do_copy
        is set, then this function performs the copying to the new location. We
        raise an error if the destination already exists.
        """

        if do_copy:
            assert obj_save_dir is not None
            assert os.path.exists(obj_save_dir)

        def serialize(obj: Any) -> Any:
            """
            Construct a serializable representation of the properties. If any
            paths exist, then copy them over.
            """

            if isinstance(obj, dict):
                return {serialize(k): serialize(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [serialize(o) for o in obj]
            else:
                if do_copy:
                    assert obj is None or isinstance(
                        obj, (int, str, float, pathlib.Path)
                    )
                    if isinstance(obj, pathlib.Path):
                        # Form the target location.
                        name = obj.name
                        base = f"{obj_save_dir}/{self.ident}"
                        os.makedirs(base, exist_ok=True)
                        path = f"{base}/{name}"
                        if os.path.exists(path):
                            raise FileExistsError(
                                f'Cannot copy file; path "{path}" already '
                                "exists."
                            )

                        # Copy it. Works for files or directories.
                        if obj.is_file():
                            shutil.copy(obj, path)
                        elif obj.is_dir():
                            shutil.copytree(obj, path)
                        else:
                            raise RuntimeError()
                        return path
                    else:
                        return obj
                else:
                    assert obj is None or isinstance(obj, (int, str, float))
                    return obj

        return {
            "artifact-ident": self.ident,
            "timestamp": self.timestamp,
            "properties": serialize(self.props),
        }

    def __eq__(self: "Artifact", other: "Artifact") -> bool:
        """
        Returns True if this artifact functionally equals the other.
        """

        if not isinstance(other, Artifact):
            return False

        return (
            self.experiment.ident == other.experiment.ident
            and self.ident == other.ident
        )

    def __str__(self: "Artifact") -> str:
        exp_id = None if self.experiment is None else self.experiment.ident
        return (
            f"Artifact("
            f"experiment_ident={exp_id}, "
            f"artifact_ident={self.ident}, "
            f"timestamp={self.timestamp}, "
            f"props={self.props})"
        )

    def __repr__(self: "Artifact") -> str:
        return str(self)
