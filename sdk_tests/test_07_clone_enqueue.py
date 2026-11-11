"""DAG-21065 B.7 - clone, override parameters, enqueue; the agent runs with the overrides."""

import pytest

from clearml import Task
from conftest import PROJECT_NAME, REPO_BRANCH, REPO_URL, unique_name, wait_for_status

pytestmark = pytest.mark.agent

BASE_PARAMS = {"General/lr": 0.1, "General/name": "base"}
OVERRIDES = {"General/lr": 0.5, "General/name": "override"}


def test_clone_enqueue_with_overrides(cleanup, queue_name):
    base = Task.create(
        project_name=PROJECT_NAME,
        task_name=unique_name("test_07_base"),
        repo=REPO_URL,
        branch=REPO_BRANCH,
        script="sdk_tests/agent_scripts/echo_params.py",
        working_directory=".",
        packages=["clearml"],
        add_task_init_call=False,
    )
    cleanup.task(base)
    base.set_parameters(BASE_PARAMS)

    clone = Task.clone(source_task=base, name=unique_name("test_07_clone"), project=base.project)
    cleanup.task(clone)
    clone.update_parameters(OVERRIDES)
    Task.enqueue(clone, queue_name=queue_name)

    wait_for_status(clone)
    clone.reload()

    assert clone.data.last_worker, "no worker recorded - the task was not run by an agent"
    assert clone.get_parameters(cast=True) == OVERRIDES

    metrics = clone.get_last_scalar_metrics()
    assert metrics["params"]["lr"]["last"] == pytest.approx(0.5)

    console = "\n".join(clone.get_reported_console_output(number_of_reports=200) or [])
    assert "name=override" in console

    # The source task is untouched.
    source = Task.get_task(task_id=base.id)
    assert source.get_parameters(cast=True) == BASE_PARAMS
    assert str(source.get_status()) == "created"
