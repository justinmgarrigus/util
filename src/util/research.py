"""
System of registering and archiving research artifacts. All experiments and 
artifacts are logged to the environment variable/secrets property 
RESEARCH_PATH.
"""

import datetime 
import json
import os
import re

from typing import Any, Dict, List, Optional 
from util.git import get_git_properties, get_git_root 
from util.secrets import get as get_secrets 


class Experiment:
    """
    An Experiment is a group of research artifacts. Each artifact within the
    experiment should have the same queryable structure.
    """
    
    _index: Optional[List[Dict[str, str]]] = None 
    _basedir: Optional[str] = None  # Root of research directory 
    _index_path: Optional[str] = None
    
    @classmethod
    def _reset(cls) -> None:
        """
        For test-cases. This resets the state of this class. 
        """

        cls._index = None
        cls._basedir = None
        cls._index_path = None 

    
    @classmethod
    def _get_basedir(cls) -> str: 
        # The user may update the base directory multiple times in a single 
        # session.
        basedir = os.environ.get("RESEARCH_PATH", None) 
        if basedir is None:
            basedir = get_secrets().get("RESEARCH_PATH")
            if basedir is None:
                raise ValueError((
                    "Error: no RESEARCH_PATH is provided as an environment "
                    "variable or in secrets."
                ))

        if cls._basedir != basedir:
            cls._index = None
            cls._basedir = basedir
            cls._index_path = None 
            if not os.path.exists(cls._basedir):
                os.makedirs(cls._basedir, exist_ok=True) 
        return cls._basedir


    @staticmethod
    def _is_index_valid(index: List["Experiment"]) -> bool:
        """
        Returns True if the entire experiment index is valid, and raises an 
        error other. 
        """
        
        def is_exp_valid(exp: "Experiment") -> bool:
            # Should contain all expected keys. 
            assert all(
                (
                    hasattr(exp, key) and 
                    isinstance(key, str) and 
                    isinstance(getattr(exp, key), str)
                )
                for key in ["name", "ident", "description", 
                    "created_timestamp", "modified_timestamp", "project_name", 
                    "commit_hash", "branch", "commit_message"]
            ), repr(exp)
            
            # Identifier must be valid.
            assert len(exp.ident) > 0
            assert (
                re.fullmatch(
                    r"^[a-zA-Z0-9\-_\.]+$", 
                    exp.ident
                )
            ), f"The identifier \"{exp.ident}\" contains illegal characters"
            assert len(exp.commit_hash) == 40 and (
                re.fullmatch(
                    f"^[a-fA-F0-9]+$", 
                    exp.commit_hash
                )
            ), f"The commit hash \"{exp.commit_hash}\" is not a valid hash"
            return True
        
        assert isinstance(index, list)
        assert all(
            is_exp_valid(exp) 
            for exp in index
        )
        return True 


    @classmethod 
    def list(cls) -> List["Experiment"]: 
        """
        Lists all experiments (equvalent to the experiment index). The index 
        keeps track of all experiments. This loads the index and additionally 
        checks it's valid. If the index does not previously exist, then it 
        creates an index file.
        """
        
        cls._get_basedir()  # Refresh this
        if cls._index is None:
            basedir = cls._get_basedir() 
            assert os.path.exists(basedir), basedir

            cls._index_path = f"{basedir}/index.json"
            if not os.path.exists(cls._index_path): 
                with open(cls._index_path, "w") as f: 
                    f.write("[]")
            with open(cls._index_path, "r") as f:
                index_json = json.load(f) 

            # Convert JSON to Experiment objects.
            cls._index = [cls(**exp) for exp in index_json]
            assert cls._is_index_valid(Experiment._index) 
         
        return cls._index 


    @classmethod
    def _save_index(cls) -> None:
        """
        Updates and saves the index file with the new experiments. After 
        creating any Experiment objects, this must be run. (It can be run 
        multiple times.) 
        """

        index = cls.list()
        assert cls._is_index_valid(index)
        assert cls._index_path is not None  # Set with list()
        assert os.path.exists(cls._index_path), Experiment._index_path  
            
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
                "commit_message": exp.commit_message 
            }
            for exp in index 
        ]

        with open(cls._index_path, "w") as f:
            json.dump(index_json, f) 

    
    @staticmethod
    def _timestamp() -> str: 
        """
        Returns the current timestamp. 
        """

        return datetime.datetime.now().strftime(
            "%m/%d/%Y @ %H:%M:%S"  # 07/01/2026 @ 15:30:00
        )


    @classmethod
    def _get(cls, experiment_ident: str) -> "Experiment":
        """
        Returns the Experiment object corresponding to the given identifier if 
        it exists or None if it doesn't exist. 
        """

        return next(
            (
                experiment
                for experiment in cls.list() 
                if experiment.ident == experiment_ident
            ), 
            None
        )


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
        commit_message: Optional[str] = None
    ) -> None:
        """
        Creates an experiment. "name" and "description" are human-readable, 
        while "ident" is unique. If the github repository is updated at all, 
        then "ident" must point to something different since the content of 
        the experiment/results obtained from it are likely different. If any
        of the project parameters are None, then they all must be None; this 
        signals that we should obtain them from the current repository instead 
        of loaded as arguments.
        
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

        self.name = name 
        self.ident = ident 
        self.description = description 
        self.created_timestamp = created_timestamp
        self.modified_timestamp = modified_timestamp
        self.project_name = project_name 
        self.commit_hash = commit_hash
        self.branch = branch 
        self.commit_message = commit_message 
        self.artifacts = []


    def save(self: "Experiment") -> None:
        """
        Saves an experiment to disk. Verifies all the parameters, too.  
        """
        
        # Obtain the contents of the index file.
        index = Experiment.list() 

        # Two conditions, existing experiments and conflicting experiments: 
        #   - An *existing experiment* is fine to append to. It represents a  
        #     case where the artifacts in that experiment, and artifacts we are
        #     likely to generate in this same Python session, probably come 
        #     from the same distribution. 
        #   - A *conflicting experiment* is not fine to append to. This is
        #     determined by the git hash being different.
        matching_idents = [exp for exp in index if exp.ident == self.ident]
        assert len(matching_idents) <= 1, repr(matching_idents) 
        if len(matching_idents) == 1: 
            old_exp = matching_idents[0] 
            if self.commit_hash != old_exp.commit_hash:
                raise ValueError((
                    "Error: you attempted to create an experiment with an "
                    f"identifier (\"{self.ident}\") that already exists in "
                    "the index. This is fine only as long as the git commits "
                    "match, which they don't. Use a new identifier instead.\n"
                    f"  Yours: hash = {self.commit_hash}, "
                    f"commit_message = {self.commit_message}\n"
                    f"  Old: hash = {old_exp.commit_hash}, "
                    f"commit_message = {old_exp.commit_message}"
                ))
            
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
            old_exp.modified_timestamp = Experiment._timestamp()
            old_exp.artifacts.extend(self.artifacts) 

        else:
            # This experiment is being created for the first time.
            self.created_timestamp = Experiment._timestamp()  
            self.modified_timestamp = Experiment._timestamp() 
            index.append(self)   
        
        # Update the general index. The index contains metadata about each 
        # artifact, but not the artifacts themselves.
        Experiment._save_index() 

        # Update the experiment-specific index.
        dname = f"{Experiment._get_basedir()}/exp-{self.ident}"
        os.makedirs(dname, exist_ok=True) 
        experiment_data = {
            "experiment-ident": self.ident, 
            "artifacts": [
                artifact.save(dname)
                for artifact in self.artifacts
            ]
        }
        index_path = f"{dname}/index.json"
        with open(index_path, "w") as f: 
            json.dump(experiment_data, f) 


    def _load_artifacts(self: "Experiment") -> List["Artifact"]: 
        """
        A given experiment contains its own index of the artifacts it contains.
        The location of this index is the same as the research base directory, 
        and the name of this index is our "ident". This returns the collection
        of artifacts for us.
        """

        basedir = Experiment._get_basedir()  
        assert os.path.exists(basedir), basedir
        exp_index = f"{basedir}/exp-{self.ident}/index.json"
        
        if os.path.exists(exp_index):
            with open(exp_index, "r") as f: 
                artifacts_json = json.load(f)
            
            # Convert JSON to Artifact objects. 
            def obj_props(json_obj: Dict[str, Any]) -> Dict[str, Any]:
                """
                The artifact object has an attribute containing all properties 
                that are not standard (i.e., are not the attribute-identifier,
                experiment-identifier, etc.). Return these. 
                """

                return {
                    key: value 
                    for key, value in json_obj.items()
                    if key not in ("attribute-ident", "experiment-ident", 
                        "timestamp") 
                }

            return [
                Artifact(
                    experiment=self, 
                    ident=art["ident"], 
                    props=obj_props(art), 
                    timestamp=art["timestamp"]
                )
                for art in artifacts_json
            ]

        else:
            # No artifacts exist yet. 
            return []


    def add_artifact(self: "Experiment", artifact: "Artifact") -> None:
        """
        Adds an artifact to our storage. Raises an error if this artifact 
        already exists.
        """

        assert not artifact.exists()
        self.artifacts.append(artifact) 


    def __str__(self: "Experiment") -> str:
        return (
            f"Experiment("
            f"ident={self.ident}, "
            f"len(artifacts)={len(self.artifacts)})"
        )


    def __repr__(self: "Experiment") -> str:
        return str(self) 

 
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
        timestamp: Optional[str] = None
    ):
        """
        Creates a new artifact. "props" are queryable. All artifacts within the
        same Experiment must contain the same properties. If any of the values 
        in this props list represent a file or directory, then they *must* be a 
        pathlib.Path object (we raise exceptions for strings that point to a 
        file/directory but are not pathlib.Path objects); these will be 
        compressed and copied into the Artifact destination, and their paths 
        will be changed to reflect the fact they're compressed + copied.
        """
    
        self.experiment = experiment
        self.ident = ident
        self.props = props
        self.timestamp = (
            timestamp if timestamp is not None 
            else Experiment._timestamp()
        )

    
    def exists(self: "Artifact") -> bool:
        """
        Returns True if this artifact exists in the index, or False otherwise. 
        This can be used to determine if we can skip an artifact-collection due
        to it already being collected.
        """

        artifacts = self.experiment._load_artifacts()
        return any(
            self.ident == art.ident
            for art in artifacts
        )


    def save(self: "Artifact", save_basedir: str) -> Dict[str, Any]:
        """
        Saves an artifact to disk. Verifies all the parameters, too. Note that
        we should *only* be saving things to an Experiment with the same git
        hash as our current git hash; if they differ, it's possible our results 
        are stale, so we should be creating a new Experiment instead. Returns
        a serialized JSON dictionary which can be saved in the index file for
        this experiment. 
        """
        
        # Copies any paths to the base directory. 
        # TODO
        
        return {
            "ident": self.ident, 
            "timestamp": self.timestamp,
            "properties": self.props
        }
