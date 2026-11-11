"""Run a two-step function pipeline: controller here, steps on the agent queue.

argv[1]: queue name
argv[2]: model URI that step1 registers
Prints: RESULT {"controller_id", "step_ids": {name: task_id}, "success"}
"""

import json
import os
import sys
import uuid

from clearml import PipelineController


def step1(model_uri):
    from clearml import OutputModel, Task

    model = OutputModel(task=Task.current_task(), name="step1_model", framework="PyTorch")
    model.update_weights(register_uri=model_uri, async_enable=False)
    return model.id


def step2(model_url):
    print(f"step2 got model_url={model_url}")
    return model_url


queue, model_uri = sys.argv[1], sys.argv[2]
project = os.environ.get("SDK_TESTS_PROJECT", "sdk-regression-tests")

pipe = PipelineController(
    name=f"test_08_pipeline-{uuid.uuid4().hex[:8]}",
    project=project,
    version="1.0.0",
    add_pipeline_tags=False,
)
pipe.set_default_execution_queue(queue)
pipe.add_function_step(
    name="step1",
    function=step1,
    function_kwargs={"model_uri": model_uri},
    function_return=["model_id"],
    packages=["clearml"],
    monitor_models=["*"],
    cache_executed_step=False,
)
pipe.add_function_step(
    name="step2",
    function=step2,
    parents=["step1"],
    function_kwargs={"model_url": "${step1.models.output.-1.url}"},
    function_return=["model_url"],
    packages=["clearml"],
    cache_executed_step=False,
)
pipe.start_locally(run_pipeline_steps_locally=False)

nodes = pipe.get_pipeline_dag()
result = {
    "controller_id": pipe.id,
    "step_ids": {name: node.executed for name, node in nodes.items()},
    "success": bool(pipe.is_successful()),
}
print("RESULT " + json.dumps(result))
