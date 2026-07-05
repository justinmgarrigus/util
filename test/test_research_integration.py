"""
Tests the entirety of the research module, mirroring a real-world use-case.
This script invokes itself with subprocesses, such that one subprocess computes
one artifact. 
"""

import argparse
import multiprocessing as mp
import os 
import pytest 
import random 
import shutil 
import subprocess
import time

from util.git import get_git_properties, get_git_root 
from util.research import Artifact, Experiment

NUM_JOBS = 100
MISSING_SUBSET_SIZE = 1
POOL_SIZE = 32
basename = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = f"{basename}/research-test-delete"  # Research data saved here


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
    os.environ["RESEARCH_PATH"] = DATA_DIR

    # Run the tests.
    yield 

    # After the test. 
    os.environ.clear()
    os.environ.update(old_environ) 
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)


def worker(job_value: int) -> str:
    """
    Runs a worker process. Produces an artifact. Has a small chance of failure;
    returns a string representing the error if one occurred, or an empty string
    if no error occurred. 
    """

    try:
        # Collect the data.
        exp = Experiment(
            name="Integration test for the Research module", 
            ident=f"integration-test", 
            description=(
                "Simple integration test for the Research module. This is run "
                "within a subprocess and communicates results directly to the "
                "index without going through the main process."
            )
        )

        artifact_ident = f"artifact-{job_value}"
        if exp.exists(artifact_ident):
            return ""  # Nothing to be done. 
        
        # Do the "computation". 
        random.seed(0)
        time.sleep(random.random()) 
        result = 1000000 + job_value
        
        # Construct the Artifact result. 
        art = Artifact(
            experiment=exp, 
            ident=artifact_ident, 
            props={
                "input": job_value,
                "output": result
            }
        )
        assert not art.exists() 
        exp.add_artifact(art) 
        assert art.exists() 
        
        # Confirm paths exist. 
        git_hash = get_git_properties()["commit_hash"][:8]  
        base = f"{DATA_DIR}/exp-integration-test-{git_hash}"
        assert os.path.exists(base) 
        assert os.path.exists(f"{base}/index.json") 
        return ""  # Success. 

    except Exception as ex:
        raise 
        return repr(ex)  # Failure.  


class TestIntegration:
    """
    Runs the integration test. 
    """

    def test_integration(self: "TestIntegration"):
        # Form the collection of work to do. Intentionally don't do every job 
        # here. 
        ignore_subset = set(
            random.randrange(NUM_JOBS) 
            for _ in range(MISSING_SUBSET_SIZE)
        )
        jobs = [
            idx 
            for idx in range(NUM_JOBS)
            if idx not in ignore_subset
        ]

        # Send each artifact to one subprocess.
        with mp.Pool(processes=POOL_SIZE) as pool:
            results = pool.map(worker, jobs) 

        # Check the status.
        assert all(len(r) == 0 for r in results), (
            "\n".join(f"{idx}: {r}" for idx, r in zip(jobs, results))
        )
        
        # Confirm the files exist. 
        git_hash = get_git_properties()["commit_hash"][:8]  
        base = f"{DATA_DIR}/exp-integration-test-{git_hash}"
        assert os.path.exists(f"{base}/index.json") 

        exps = Experiment.list() 
        assert len(exps) == 1 
        exp = exps[0]
        assert len(exp.artifacts) == len(jobs)
        for art in exp.artifacts: 
            assert art.props["output"] == art.props["input"] + 1000000

        # Repeat the above for the missing experiments. Re-run *all* 
        # experiments, and trust the subprocess doesn't attempt to re-do any
        # experiments that are already complete, since that would result in an 
        # error. 
        with mp.Pool(processes=POOL_SIZE) as pool:
            results = pool.map(worker, [i for i in range(NUM_JOBS)])

        # Check the status.
        assert all(len(r) == 0 for r in results), (
            "\n".join(f"{idx}: {r}" for idx in jobs)
        )
        
        assert len(Experiment.list()) == 1 
        assert len(exp.artifacts) == NUM_JOBS
        for art in exp.artifacts: 
            assert art.props["output"] == art.props["input"] + 1000000
