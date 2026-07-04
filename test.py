"""
Tests out the research utilities.
"""

import random 

from util.research import Artifact, Experiment


exp = Experiment(
    name="Simple test", 
    ident="simple-test",
    description=(
        "Simple test for verifying the experiment/artifact interface is "
        "correctly working"
    )
)

artifacts = [
    Artifact(
        experiment=exp, 
        ident=f"art-{i}", 
        props={
            "stuff": random.randrange(1, 100), 
            "index": i
        }
    )
    for i in range(10) 
]
for art in artifacts:
    exp.add_artifact(art)
exp.save() 
