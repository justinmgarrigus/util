"""
Tests the research scripts (Artifact, Experiment).
"""

import json
import os
import pathlib
import pytest
import shutil
import time

from util.etc import AtomicFile
from util.git import get_git_properties
from util.research import Artifact, Experiment


basename = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = f"{basename}/research-test-delete"  # Research data saved here
DATA_DIR_2 = f"{DATA_DIR}-2"  # For testing multiple archives
SECRETS_YAML_LOC = f"{basename}/test-secrets.yaml"  # Test yaml file
MEDIA_DIR = f"{basename}/test-media"  # Where media for copying is stored


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
    if os.path.exists(MEDIA_DIR):
        shutil.rmtree(MEDIA_DIR)


class TestEtc:
    """
    Tests miscellaneous functionality.
    """

    def test_atomic_file(self: "TestEtc") -> None:
        """
        Ensures the atomic file works the same as a regular file.
        """

        os.makedirs(DATA_DIR)
        with AtomicFile(f"{DATA_DIR}/test.txt", "w") as f:
            f.write("hello")
        with AtomicFile(f"{DATA_DIR}/test.txt", "r") as f:
            text = f.read()
        assert text == "hello"


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
        exp._save()

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
                os.O_WRONLY  # Write only
                | os.O_CREAT  # Create if not exists
                | os.O_TRUNC  # Truncate the file to zero
            ),
            mode=0o600,
        )
        with open(descriptor, "w") as f:
            f.write(f'RESEARCH_PATH: "{DATA_DIR}"')

        exp = Experiment(name="a", ident="b", description="c")
        exp._save()

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
            exp._save()
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
                os.O_WRONLY  # Write only
                | os.O_CREAT  # Create if not exists
                | os.O_TRUNC  # Truncate the file to zero
            ),
            mode=0o600,
        )
        exp = Experiment(name="a", ident="b", description="c")

        # Malformed secret file.
        with open(descriptor, "w") as f:
            f.write("abc")

        try:
            exp._save()
            raise RuntimeError()
        except AssertionError:
            pass

    def test_path_not_cached(self: "TestDirectoryConstruction") -> None:
        """
        Ensures that if we were to change the experiment save directory, it
        would actually update.
        """

        assert not os.path.exists(DATA_DIR)
        assert not os.path.exists(DATA_DIR_2)
        exp = Experiment(name="a", ident="b", description="c")

        os.environ["RESEARCH_PATH"] = DATA_DIR
        exp._save()
        assert os.path.exists(DATA_DIR)
        assert not os.path.exists(DATA_DIR_2)
        shutil.rmtree(DATA_DIR)

        os.environ["RESEARCH_PATH"] = DATA_DIR_2
        exp._save()
        assert not os.path.exists(DATA_DIR)
        assert os.path.exists(DATA_DIR_2)


class TestExperiment:
    """
    Tests that experiment saving and representation is correct.
    """

    def test_multi_save(self: "TestExperiment") -> None:
        """
        Confirms we can save multiple separate experiments.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)

        exp1 = Experiment(name="a", ident="a", description="a")
        exp1._save()
        exp2 = Experiment(name="b", ident="b", description="b")
        exp2._save()
        exp3 = Experiment(name="c", ident="c", description="c")
        exp3._save()

        assert Experiment.list() == [exp1, exp2, exp3]
        assert os.path.exists(DATA_DIR)

    def test_ident_name(self: "TestExperiment") -> None:
        """
        Identifiers represent file names, so no strange characters.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR

        for idx, ident in enumerate(
            ["", "hello!", "foo bar", "abc@def", "comma,comma"]
        ):
            try:
                exp = Experiment(
                    name=f"test{idx}", ident=ident, description=f"test{idx}"
                )
                exp._save()
                raise RuntimeError(f'Did not raise: "{ident}"')
            except AssertionError:
                pass

    def test_partial_git_params(self: "TestExperiment") -> None:
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
            commit_message="h",
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
                commit_message="h",
            )
            raise RuntimeError()
        except AssertionError:
            pass

    def test_incorrect_git_hash(self: "TestExperiment") -> None:
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
                commit_message="h",
            )._save()
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
                commit_message="h",
            )._save()
            raise RuntimeError()
        except AssertionError:
            pass

    def test_duplicate_experiment_fine(self: "TestExperiment") -> None:
        """
        We **can** have two experiments with the same identifier. This likely
        represents a case where the same experiment is written across two
        different Python sessions.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR

        exp1 = Experiment(name="a", ident="foo", description="a")
        exp2 = Experiment(name="b", ident="foo", description="b")

        exp1._save()
        exp2._save()  # No error
        assert len(Experiment.list()) == 1

    def test_duplicate_experiment_bad(self: "TestExperiment") -> None:
        """
        We **can** have two experiments with the same identifier if the Git
        hash changed, but they must result in different Experiment objects.
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
            commit_message="h",
        )
        exp2 = Experiment(
            name="a",
            ident="i",  # Different identifier, new experiment
            description="c",
            created_timestamp="d",
            modified_timestamp="e",
            project_name="f",
            commit_hash="1111111111111111111111111111111111111111",
            branch="g",
            commit_message="h",
        )
        exp3 = Experiment(
            name="a",
            ident="b",  # Same identifier but different hash, new experiment
            description="c",
            created_timestamp="d",
            modified_timestamp="e",
            project_name="f",
            commit_hash="1111111111111111111111111111111111111111",
            branch="g",
            commit_message="h",
        )
        exp4 = Experiment(
            name="z",
            ident="i",  # Same identifier and same hash, so same experiment
            description="z",
            created_timestamp="z",
            modified_timestamp="z",
            project_name="f",
            commit_hash="1111111111111111111111111111111111111111",
            branch="g",
            commit_message="h",
        )

        assert len(Experiment.list()) == 0
        exp1._save()
        assert len(Experiment.list()) == 1
        exp2._save()
        assert len(Experiment.list()) == 2
        exp3._save()
        assert len(Experiment.list()) == 3
        exp4._save()
        assert len(Experiment.list()) == 3

    def test_multi_save_same_object(self: "TestExperiment") -> None:
        """
        Saving the same experiment multiple times is fine.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert len(Experiment.list()) == 0

        exp = Experiment(name="a", ident="b", description="c")
        for i in range(100):
            exp._save()

        assert len(Experiment.list()) == 1

    def test_experiment_index_json(self: "TestExperiment") -> None:
        """
        Ensures the experiment index JSON file is correct. The user may want to
        read this manually, so we should allow them to. (Editing it would be
        highly discouraged though, they should do that through the SDK.)
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)

        exp = Experiment(name="a", ident="unique_identifier", description="c")
        exp._save()
        assert os.path.exists(DATA_DIR)
        assert os.path.exists(f"{DATA_DIR}/index.json")

        with open(f"{DATA_DIR}/index.json", "r") as f:
            # This file should contain a list of experiments. None of the
            # fields in experiments should be None.
            data = json.load(f)
            assert isinstance(data, list)
            assert len(data) == 1
            assert isinstance(data[0], dict)
            assert "ident" in data[0]
            assert data[0]["ident"] == "unique_identifier"
            assert all(isinstance(v, str) for v in data[0].values())

    def test_saved_timestamp(self: "TestExperiment") -> None:
        """
        Saving a new experiment should set its creation timestamp.
        """

        start_time = Experiment.timestamp()
        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)

        exp = Experiment(name="a", ident="b", description="c")
        exp._save()

        exps = Experiment.list()
        assert len(exps) == 1
        assert (
            Experiment.timestamp(exps[0].created_timestamp)
            - Experiment.timestamp(start_time)
        ).seconds <= 1  # Faster than one second

    def test_modified_timestamp(self: "TestExperiment") -> None:
        """
        Modifying an experiment should *not* change its creation timestamp,
        but *should* change its modified timestamp.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)

        exp = Experiment(name="a", ident="foo", description="c")
        exp._save()

        created_timestamp = exp.created_timestamp
        modified_timestamp = exp.modified_timestamp

        # Wait one second so the times change.
        time.sleep(1)

        # Different experiment object but same identifier with same git commit
        # details means it represents the same experiment.
        exp = Experiment(name="x", ident="foo", description="y")
        exp._save()

        assert created_timestamp == exp.created_timestamp
        assert modified_timestamp != exp.modified_timestamp


class TestArtifact:
    """
    Tests that artifact saving and representation is correct.
    """

    def test_artifact_index_json(self: "TestArtifact") -> None:
        """
        Ensures the artifact index JSON file is correct and present.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)
        git_hash = get_git_properties()["commit_hash"][:8]

        exp = Experiment(name="a", ident="foo", description="c")
        art = Artifact(experiment=exp, ident="art0", props={"x": 1})
        exp.add_artifact(art)
        assert os.path.exists(DATA_DIR)
        assert os.path.exists(f"{DATA_DIR}/index.json")
        assert os.path.exists(f"{DATA_DIR}/exp-foo-{git_hash}/index.json")

        with open(f"{DATA_DIR}/exp-foo-{git_hash}/index.json", "r") as f:
            # This file should contain a list of artifacts. None of the
            # fields in experiments should be None.
            data = json.load(f)
            assert isinstance(data, dict)
            assert all(k in data.keys() for k in ("experiment-ident", "artifacts"))
            assert data["experiment-ident"] == "foo"
            assert isinstance(data["artifacts"], list)
            assert len(data["artifacts"]) == 1
            assert isinstance(data["artifacts"][0], dict)
            assert all(
                (
                    k in data["artifacts"][0].keys()
                    and data["artifacts"][0][k] is not None
                )
                for k in ("artifact-ident", "properties", "timestamp")
            )
            assert data["artifacts"][0]["artifact-ident"] == "art0"
            assert data["artifacts"][0]["properties"] == {"x": 1}

    def test_no_exist(self: "TestArtifact") -> None:
        """
        An artifact should not exist until it is saved.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)

        exp = Experiment(name="a", ident="b", description="c")
        art = Artifact(experiment=exp, ident="artifact0", props={"x": 1})
        assert not art.exists()

        # Artifact must be explicitly added.
        exp._save()
        assert not art.exists()

        exp.add_artifact(art)
        assert art.exists()

    def test_no_duplicate_ident(self: "TestArtifact") -> None:
        """
        Artifacts are identified by their identifier, so there cannot be
        duplicates.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        assert not os.path.exists(DATA_DIR)

        exp = Experiment(name="a", ident="b", description="c")
        art = Artifact(experiment=exp, ident="unique", props={"x": 1})
        assert not exp.exists(art.ident)
        exp.add_artifact(art)

        # First, saving the same instance should result in an error.
        assert art.exists()
        try:
            exp.add_artifact(art)
            raise ValueError
        except AssertionError:
            pass

        # Second, a different instance with the same data results in an error.
        art_dup = Artifact(experiment=exp, ident="unique", props={"x": 1})
        assert art_dup.exists()
        try:
            exp.add_artifact(art_dup)
            raise ValueError
        except AssertionError:
            pass

    def test_multi_save_no_crossover(self: "TestArtifact") -> None:
        """
        Ensures that saving artifacts to one experiment will not show up in
        another experiment.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR

        exp1 = Experiment(name="a", ident="foo", description="b")
        art1 = Artifact(experiment=exp1, ident="art1", props={"x": 1})
        exp1.add_artifact(art1)

        exp2 = Experiment(name="a", ident="bar", description="b")
        art2 = Artifact(experiment=exp2, ident="art2", props={"x": 1})
        exp2.add_artifact(art2)

        exps = Experiment.list()
        for exp in exps:
            assert len(exp.artifacts) == 1
            if exp.ident == "foo":
                assert exp == exp1
                assert exp.artifacts[0] == art1
            elif exp.ident == "bar":
                assert exp == exp2
                assert exp.artifacts[0] == art2
            else:
                raise ValueError()

    def test_save_art_different_experiment(self: "TestArtifact") -> None:
        """
        We cannot save an artifact to an experiment it doesn't belong to.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR

        exp1 = Experiment(name="a", ident="foo", description="b")
        art1 = Artifact(experiment=exp1, ident="art1", props={"x": 1})
        exp1.add_artifact(art1)

        exp2 = Experiment(name="a", ident="bar", description="b")
        art2 = Artifact(experiment=exp2, ident="art2", props={"x": 1})
        exp2.add_artifact(art2)

        try:
            exp1.add_artifact(art2)
            raise RuntimeError()
        except AssertionError:
            pass

    def test_no_caching(self: "TestArtifact") -> None:
        """
        The result of Experiment.list() is not the same Experiment objects as
        what was originally inserted. They are *functionally equivalent*, but
        represent different objects.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR

        exp1 = Experiment(name="a", ident="foo", description="b")
        art1 = Artifact(experiment=exp1, ident="art1", props={"x": 1})
        exp1.add_artifact(art1)

        exp2 = Experiment(name="a", ident="bar", description="b")
        art2 = Artifact(experiment=exp2, ident="art2", props={"x": 1})
        exp2.add_artifact(art2)

        exps = Experiment.list()
        assert exp1 in exps
        assert exp2 in exps
        obtained_exp1 = next(e for e in exps if e == exp1)
        obtained_exp2 = next(e for e in exps if e == exp2)
        assert exp1 is not obtained_exp1
        assert exp2 is not obtained_exp2

    def test_copy_file(self: "TestArtifact") -> None:
        """
        Tests that passing a file as a property means it gets copied to the
        target directory.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        ident = "foo"
        fname = "abc.txt"
        exp = Experiment(name="a", ident=ident, description="b")

        path = f"{MEDIA_DIR}/{fname}"
        assert not os.path.exists(MEDIA_DIR)
        os.makedirs(MEDIA_DIR)
        with open(path, "w") as f:
            f.write("test_copy_file 123")
        art = Artifact(
            experiment=exp, ident="art", props={"my_file": pathlib.Path(path)}
        )
        exp.add_artifact(art)

        # Delete original directory to confirm it's a copy.
        shutil.rmtree(MEDIA_DIR)

        git_hash = get_git_properties()["commit_hash"][:8]
        new_path = f"{DATA_DIR}/exp-{ident}-{git_hash}/art/{fname}"
        stored_exp = Experiment.list()
        art = stored_exp[0].artifacts[0]
        assert str(art.props["my_file"]) == new_path

        assert os.path.exists(new_path), new_path
        with open(new_path, "r") as f:
            assert f.read() == "test_copy_file 123"

    def test_copy_multiple_files(self: "TestArtifact") -> None:
        """
        Copies multiple files within a single artifact.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        exp = Experiment(name="a", ident="foo", description="b")

        assert not os.path.exists(MEDIA_DIR)
        os.makedirs(MEDIA_DIR)
        props = {}
        for idx in range(3):
            path = f"{MEDIA_DIR}/item-{idx}.md"
            with open(path, "w") as f:
                f.write(f"test_copy_multiple_files {idx}")
            props[f"data-{idx}"] = pathlib.Path(path)

        art = Artifact(experiment=exp, ident="art", props=props)
        exp.add_artifact(art)

        # Delete original directory to confirm it's a copy.
        shutil.rmtree(MEDIA_DIR)

        stored_exp = Experiment.list()
        art = stored_exp[0].artifacts[0]
        assert all(
            (f"data-{idx}" in art.props and os.path.exists(art.props[f"data-{idx}"]))
            for idx in range(3)
        )
        for idx in range(3):
            new_path = art.props[f"data-{idx}"]
            with open(new_path, "r") as f:
                assert f.read() == f"test_copy_multiple_files {idx}"

    def test_copy_multiple_files_per_artifact(self: "TestArtifact") -> None:
        """
        Copies multiple files per artifact.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR

        assert not os.path.exists(MEDIA_DIR)
        os.makedirs(MEDIA_DIR)
        for idx in range(3):
            path = f"{MEDIA_DIR}/item-{idx}.md"
            with open(path, "w") as f:
                f.write(f"test_copy_multiple_files_per_artifact {idx}")

            exp = Experiment(name="a", ident=f"foo{idx}", description="b")
            art = Artifact(
                experiment=exp, ident="art", props={"fname": pathlib.Path(path)}
            )
            exp.add_artifact(art)

        # Delete original directory to confirm it's a copy.
        shutil.rmtree(MEDIA_DIR)

        stored_exps = Experiment.list()
        for idx in range(3):
            exp = next(exp for exp in stored_exps if exp.ident == f"foo{idx}")
            art = exp.artifacts[0]
            with open(art.props["fname"], "r") as f:
                assert f.read() == f"test_copy_multiple_files_per_artifact {idx}"

    def test_copy_directory(self: "TestArtifact") -> None:
        """
        Copies an entire directory instead of just a file.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        exp = Experiment(name="a", ident="foo", description="b")

        assert not os.path.exists(MEDIA_DIR)
        os.makedirs(MEDIA_DIR)
        for idx in range(3):
            with open(f"{MEDIA_DIR}/item-{idx}.md", "w") as f:
                f.write(f"test_copy_directory {idx}")

        art = Artifact(
            experiment=exp, ident="art", props={"dname": pathlib.Path(MEDIA_DIR)}
        )
        exp.add_artifact(art)

        # Delete original directory to confirm it's a copy.
        shutil.rmtree(MEDIA_DIR)

        stored_exp = Experiment.list()
        art = stored_exp[0].artifacts[0]
        assert "dname" in art.props.keys()
        git_hash = get_git_properties()["commit_hash"][:8]
        path = f"{DATA_DIR}/exp-foo-{git_hash}/art/{os.path.basename(MEDIA_DIR)}"
        assert str(art.props["dname"]) == path
        assert os.path.exists(path)
        for idx in range(3):
            with open(f"{art.props['dname']}/item-{idx}.md", "r") as f:
                assert f.read() == f"test_copy_directory {idx}"

    def test_copy_file_str(self: "TestArtifact") -> None:
        """
        Confirms that for Artifacts, we can't have a property with a value
        that's a file path due to it being ambiguous whether it should be
        copied.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        os.makedirs(MEDIA_DIR)

        path = f"{MEDIA_DIR}/foo.txt"
        with open(path, "w") as f:
            f.write("abc")

        exp = Experiment(name="a", ident="foo", description="b")

        try:
            Artifact(experiment=exp, ident="art", props={"path": path})
            raise RuntimeError()
        except ValueError:
            pass

    def test_serializable(self: "TestArtifact") -> None:
        """
        We can't have a property that's not serializable, like a custom class.
        """

        class TestClass:
            pass

        os.environ["RESEARCH_PATH"] = DATA_DIR
        exp = Experiment(name="a", ident="foo", description="b")
        art = Artifact(experiment=exp, ident="art", props={"foo": TestClass()})

        try:
            exp.add_artifact(art)
            raise ValueError()
        except AssertionError:
            pass

    def test_schema_wrong(self: "TestArtifact") -> None:
        """
        Tests that two artifacts having different schemas results in an error.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        exp = Experiment(name="a", ident="foo", description="b")
        art1 = Artifact(experiment=exp, ident="v1.2.3", props={"foo": 1})
        art2 = Artifact(experiment=exp, ident="art", props={"bar": 1})
        exp.add_artifact(art1)
        try:
            exp.add_artifact(art2)
            raise RuntimeError()
        except AssertionError:
            pass

    def test_schema_type(self: "TestArtifact") -> None:
        """
        Tests that the schema also checks for the types of properties.
        """

        os.environ["RESEARCH_PATH"] = DATA_DIR
        exp = Experiment(name="a", ident="foo", description="b")
        art1 = Artifact(experiment=exp, ident="art", props={"foo": 1})
        art2 = Artifact(experiment=exp, ident="art", props={"foo": "bar"})
        exp.add_artifact(art1)
        try:
            exp.add_artifact(art2)
            raise RuntimeError()
        except AssertionError:
            pass
