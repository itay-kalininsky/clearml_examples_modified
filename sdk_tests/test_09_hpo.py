"""DAG-21065 B.9 - HPO: RandomSearch, 2 parameters, 3 jobs on the agent."""

import pytest

from clearml import Task
from conftest import AGENT_TIMEOUT, PROJECT_NAME, REPO_BRANCH, REPO_URL, run_script, unique_name, wait_for_status

pytestmark = pytest.mark.agent


def _objective(x, y):
    return x * (2 if y == "b" else 1)


def test_hpo_random_search(cleanup, queue_name):
    base = Task.create(
        project_name=PROJECT_NAME,
        task_name=unique_name("test_09_hpo_base"),
        repo=REPO_URL,
        branch=REPO_BRANCH,
        script="sdk_tests/agent_scripts/hpo_base.py",
        working_directory=".",
        packages=["clearml"],
        add_task_init_call=False,
    )
    cleanup.task(base)
    base.add_tags([cleanup.tag])
    base.set_parameters({"General/x": 1, "General/y": "a"})

    result = run_script(
        "run_hpo.py", base.id, queue_name, AGENT_TIMEOUT / 60.0, timeout=AGENT_TIMEOUT + 120, run_tag=cleanup.tag
    )
    cleanup.task(result["controller_id"])
    jobs = result["jobs"]
    for tid in jobs:
        cleanup.task(tid)

    assert len(jobs) == 3, f"expected 3 child tasks, got {jobs}"

    objectives = {}
    for tid, sampled in jobs.items():
        child = Task.get_task(task_id=tid)
        wait_for_status(child)
        params = child.get_parameters(cast=True)
        x, y = int(params["General/x"]), str(params["General/y"])

        assert 1 <= x <= 10, (tid, x)
        assert y in ("a", "b"), (tid, y)
        # What the child holds matches what the optimizer says it sampled.
        assert str(sampled["General/x"]) == str(x), (tid, sampled, params)
        assert str(sampled["General/y"]) == y, (tid, sampled, params)

        reported = child.get_last_scalar_metrics()["objective"]["value"]["last"]
        assert reported == pytest.approx(_objective(x, y)), (tid, x, y, reported)
        objectives[tid] = reported

    # The optimizer reports the same children, best first.
    top = result["top"]
    assert top, "get_top_experiments() returned nothing"
    assert set(top) <= set(jobs)
    top_values = [objectives[tid] for tid in top]
    assert top_values == sorted(top_values, reverse=True)
