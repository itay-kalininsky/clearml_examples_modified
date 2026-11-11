"""DAG-21065 B.8 - pipeline: step2 consumes ${step1.models.output.-1.url}."""

import pytest

from clearml import Task
from conftest import AGENT_TIMEOUT, run_script, unique_uri

pytestmark = pytest.mark.agent


def test_pipeline_model_reference(cleanup, queue_name):
    model_uri = unique_uri("step1.pt")
    result = run_script("run_pipeline.py", queue_name, model_uri, timeout=AGENT_TIMEOUT)

    controller = Task.get_task(task_id=result["controller_id"])
    step_ids = result["step_ids"]
    for tid in [*step_ids.values(), controller.id]:
        if tid:
            cleanup.task(tid)

    assert result["success"], f"pipeline failed: {result}"
    assert step_ids.get("step1") and step_ids.get("step2"), step_ids

    step1 = Task.get_task(task_id=step_ids["step1"])
    step2 = Task.get_task(task_id=step_ids["step2"])
    step1_models = step1.models["output"]
    for m in step1_models:
        cleanup.model(m.id)

    assert len(step1_models) >= 1
    assert step1_models[-1].url == model_uri
    assert step2.get_parameters().get("kwargs/model_url") == model_uri

    # The controller lists the steps' output models (monitor_models=["*"]).
    controller.reload()
    controller_model_ids = {m.id for m in controller.models["output"]}
    assert step1_models[-1].id in controller_model_ids
    assert str(controller.get_status()) in ("completed", "closed")
