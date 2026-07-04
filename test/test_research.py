"""
Tests the research scripts (Artifact, Experiment).
"""

import json
import os
import pathlib
import pytest 
import shutil 
import sys
import tempfile
 
from util import git as git_module
from util import secrets as secrets_module
from util.research import Artifact, Experiment


basename = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = f"{basename}/research-test-delete"  # Research data saved here
DATA_DIR_2 = f"{DATA_DIR}-2"  # For testing multiple archives  
SECRETS_YAML_LOC = f"{basename}/test-secrets.yaml"  # Test yaml file


@pytest.fixture(autouse=True)
def test_setup_teardown():
    """
    Code run before and after each test. Used to configure the environment 
    variables.
    """

    # Before the test.
    old_environ = dict(os.environ)
    os.environ.pop("RESEARCH_PATH", default=None) 
    os.environ.pop("UTIL_SECRETS_PATH", default=None)
    Experiment._reset() 

    # Run the tests.
    yield 

    # After the test. 
    os.environ.clear()
    os.environ.update(old_environ) 
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    if os.path.exists(DATA_DIR_2):
        shutil.rmtree(DATA_DIR_2)
    if os.path.exists(SECRETS_YAML_LOC):
        os.remove(SECRETS_YAML_LOC)


class TestDirectoryConstruction:
    """
    Asserts that the directory is constructed correctly.
    """

    def test_save_loc_env(self: "TestDirectoryConstruction") -> None:
        """
        If the environment variable is set, the project should be saved to the 
        same location.
        """
        
        assert "RESEARCH_PATH" not in os.environ
        assert not os.path.exists(DATA_DIR)
    
        os.environ["RESEARCH_PATH"] = DATA_DIR
        exp = Experiment(name="a", ident="b", description="c")
        exp.save() 
        
        assert os.path.exists(DATA_DIR)
    
    
    def test_save_loc_secrets(self: "TestDirectoryConstruction") -> None:
        """
        If the environment variable is not set, the project should be saved to 
        the same place as wherever's set in the secrets file. 
        """
        
        assert "RESEARCH_PATH" not in os.environ
        assert "UTIL_SECRETS_PATH" not in os.environ
        assert not os.path.exists(DATA_DIR)
        assert not os.path.exists(SECRETS_YAML_LOC)
        
        os.environ["UTIL_SECRETS_PATH"] = SECRETS_YAML_LOC
        descriptor = os.open(
            path=SECRETS_YAML_LOC, 
            flags=(
                os.O_WRONLY |  # Write only 
                os.O_CREAT  |  # Create if not exists
                os.O_TRUNC     # Truncate the file to zero 
            ),
            mode=0o600
        )
        with open(descriptor, "w") as f:
            f.write(f"RESEARCH_PATH: \"{DATA_DIR}\"")
        
        exp = Experiment(name="a", ident="b", description="c")
        exp.save() 
        
        assert os.path.exists(DATA_DIR)
    
    
    def test_save_loc_missing(self: "TestDirectoryConstruction") -> None:
        """
        If no environment variable nor secrets file is provided, raise an 
        error. 
        """
    
        assert "RESEARCH_PATH" not in os.environ
        assert "UTIL_SECRETS_PATH" not in os.environ
        assert not os.path.exists(DATA_DIR)
        assert not os.path.exists(SECRETS_YAML_LOC)
        os.environ["UTIL_SECRETS_PATH"] = ""
        
        exp = Experiment(name="a", ident="b", description="c")
        try:
            exp.save()
            raise RuntimeError() 
        except FileNotFoundError: 
            pass
    
    
    def test_malformed_path(self: "TestDirectoryConstruction") -> None:
        """
        Tests what would happen if the secrets file was malformed. 
        """
    
        assert "RESEARCH_PATH" not in os.environ
        assert "UTIL_SECRETS_PATH" not in os.environ
        assert not os.path.exists(DATA_DIR)
        assert not os.path.exists(SECRETS_YAML_LOC)
        os.environ["UTIL_SECRETS_PATH"] = SECRETS_YAML_LOC
        descriptor = os.open(
            path=SECRETS_YAML_LOC, 
            flags=(
                os.O_WRONLY |  # Write only 
                os.O_CREAT  |  # Create if not exists
                os.O_TRUNC     # Truncate the file to zero 
            ),
            mode=0o600
        )
        exp = Experiment(name="a", ident="b", description="c") 
        
        # Malformed secret file. 
        with open(descriptor, "w") as f:
            f.write(f"abc")
    
        try:
            exp.save()
            raise RuntimeError()
        except AssertionError: 
            pass
    
    
    def test_path_not_cached(self: "TestDirectoryConstruction"):
        """
        Ensures that if we were to change the experiment save directory, it 
        would actually update. 
        """
        
        assert not os.path.exists(DATA_DIR)
        assert not os.path.exists(DATA_DIR_2)
        exp = Experiment(name="a", ident="b", description="c") 
        
        os.environ["RESEARCH_PATH"] = DATA_DIR 
        exp.save() 
        assert os.path.exists(DATA_DIR)
        assert not os.path.exists(DATA_DIR_2)
        shutil.rmtree(DATA_DIR)
    
        os.environ["RESEARCH_PATH"] = DATA_DIR_2 
        exp.save() 
        assert not os.path.exists(DATA_DIR)
        assert os.path.exists(DATA_DIR_2)


class TestExperiment:
    """
    Tests that experiment saving and representation is correct. 
    """

    def test_multi_save(self: "TestExperiment"):
        """
        Confirms we can save multiple separate experiments. 
        """
        
        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)
    
        exp1 = Experiment(name="a", ident="a", description="a")
        exp1.save() 
        exp2 = Experiment(name="b", ident="b", description="b")
        exp2.save() 
        exp3 = Experiment(name="c", ident="c", description="c")
        exp3.save() 
    
        assert Experiment.list() == [exp1, exp2, exp3]
        assert os.path.exists(DATA_DIR)
     
    
    def test_ident_name(self: "TestExperiment"):
        """
        Identifiers represent file names, so no strange characters. 
        """
    
        os.environ["RESEARCH_PATH"] = DATA_DIR
        
        for idx, ident in enumerate(
            ["", "hello!", "foo bar", "abc@def", "comma,comma"]
        ):
            try:
                exp = Experiment(
                    name=f"test{idx}", 
                    ident=ident, 
                    description=f"test{idx}"
                )
                exp.save() 
                raise RuntimeError(f"Did not raise: \"{ident}\"") 
            except AssertionError:
                pass
    

    def test_partial_git_params(self: "TestExperiment"):
        """
        When constructing an Experiment, the git parameters must be either 
        entirely provided or entirely not provided. 
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        Experiment(
            name="a", 
            ident="b", 
            description="c", 
            created_timestamp="d", 
            modified_timestamp="e", 
            project_name="f", 
            commit_hash="0000000000000000000000000000000000000000",
            branch="g", 
            commit_message="h"
        )
        try:  # Missing hash 
            Experiment(
                name="a", 
                ident="b", 
                description="c", 
                created_timestamp="d", 
                modified_timestamp="e", 
                project_name="f", 
                branch="g", 
                commit_message="h"
            )
            raise RuntimeError() 
        except AssertionError:
            pass


    def test_incorrect_git_hash(self: "TestExperiment"):
        """
        If a git hash is provided, it must be a valid hash.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        try:  # Not hex
            Experiment(
                name="a", 
                ident="foo", 
                description="c", 
                created_timestamp="d", 
                modified_timestamp="e", 
                project_name="f", 
                commit_hash="hello", 
                branch="g", 
                commit_message="h"
            ).save() 
            raise RuntimeError 
        except AssertionError:
            pass
        try:  # Not 40 characters (39 characters here) 
            Experiment(
                name="a", 
                ident="bar", 
                description="c", 
                created_timestamp="d", 
                modified_timestamp="e", 
                project_name="f", 
                commit_hash="000000000000000000000000000000000000000", 
                branch="g", 
                commit_message="h"
            ).save()
            raise RuntimeError() 
        except AssertionError:
            pass 

    
    def test_duplicate_experiment_fine(self: "TestExperiment"):
        """
        We **can** have two experiments with the same identifier. This likely 
        represents a case where the same experiment is written across two 
        different Python sessions. 
        """
    
        os.environ["RESEARCH_PATH"] = DATA_DIR
    
        exp1 = Experiment(name="a", ident="foo", description="a")
        exp2 = Experiment(name="b", ident="foo", description="b")
        
        exp1.save()
        exp2.save()  # No error  
    
    
    def test_duplicate_experiment_bad(self: "TestExperiment"):
        """
        We **cannot** have two experiments with the same identifier if the Git
        hash changed. 
        """
    
        os.environ["RESEARCH_PATH"] = DATA_DIR

        exp1 = Experiment(
            name="a", 
            ident="b", 
            description="c", 
            created_timestamp="d", 
            modified_timestamp="e", 
            project_name="f", 
            commit_hash="0000000000000000000000000000000000000000",
            branch="g", 
            commit_message="h"
        )
        exp2 = Experiment(
            name="a", 
            ident="i",  # Different identifier, should be fine 
            description="c", 
            created_timestamp="d", 
            modified_timestamp="e", 
            project_name="f", 
            commit_hash="1111111111111111111111111111111111111111",
            branch="g", 
            commit_message="h"
        )
        exp3 = Experiment(
            name="a", 
            ident="b",  # Same identifier but different hash, bad  
            description="c", 
            created_timestamp="d", 
            modified_timestamp="e", 
            project_name="f", 
            commit_hash="1111111111111111111111111111111111111111",
            branch="g", 
            commit_message="h"
        )

        exp1.save()
        exp2.save()
        try:
            exp3.save()
            raise RuntimeError() 
        except ValueError:
            pass

    
    def test_multi_save(self: "TestExperiment"):
        """
        Saving the same experiment multiple times is fine.
        """
    
        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert len(Experiment.list()) == 0
        
        exp = Experiment(name="a", ident="b", description="c")
        for i in range(100):
            exp.save() 

        assert len(Experiment.list()) == 1 


    def test_experiment_index_json(self: "TestExperiment"):
        """
        Ensures the experiment index JSON file is correct. The user may want to 
        read this manually, so we should allow them to. (Editing it would be 
        highly discouraged though, they should do that through the SDK.)
        """

        pass


    def test_saved_timestamp(self: "TestExperiment"): 
        """
        Saving a new experiment should set its creation timestamp.
        """

        pass


    def test_modified_timestamp(self: "TestExperiment"):
        """
        Modifying an experiment should *not* change its creation timestamp, 
        but *should* change its modified timestamp. 
        """

        pass


class TestArtifact:
    """
    Tests that artifact saving and representation is correct. 
    """

    def test_multi_save_no_crossover(self: "TestArtifact"):
        """
        Ensures that saving artifacts to one experiment will not show up in 
        another experiment. 
        """
    
        pass
