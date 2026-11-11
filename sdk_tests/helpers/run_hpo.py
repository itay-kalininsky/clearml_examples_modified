"""Run a RandomSearch HPO (3 jobs, 2 parameters) on the agent queue.

argv[1]: base task id
argv[2]: queue name
argv[3]: time limit in minutes
Prints: RESULT {"controller_id", "jobs": {task_id: params}, "top": [task_id, ...]}
"""

import json
import os
import sys

from clearml import Task
from clearml.automation import (
    DiscreteParameterRange,
    HyperParameterOptimizer,
    RandomSearch,
    UniformIntegerParameterRange,
)

base_task_id, queue, limit_min = sys.argv[1], sys.argv[2], float(sys.argv[3])

controller = Task.init(
    project_name=os.environ.get("SDK_TESTS_PROJECT", "sdk-regression-tests"),
    task_name="test_09_hpo-controller",
    task_type=Task.TaskTypes.optimizer,
    reuse_last_task_id=False,
    auto_connect_frameworks=False,
    auto_resource_monitoring=False,
    auto_connect_arg_parser=False,
    tags=[os.environ["SDK_TESTS_RUN_TAG"]],  # lets the test clean up even if this script times out
)

opt = HyperParameterOptimizer(
    base_task_id=base_task_id,
    hyper_parameters=[
        UniformIntegerParameterRange("General/x", min_value=1, max_value=10),
        DiscreteParameterRange("General/y", values=["a", "b"]),
    ],
    objective_metric_title="objective",
    objective_metric_series="value",
    objective_metric_sign="max",
    optimizer_class=RandomSearch,
    execution_queue=queue,
    max_number_of_concurrent_tasks=1,
    total_max_jobs=3,
    pool_period_min=0.1,
    optimization_time_limit=limit_min,
)
opt.start()
opt.wait()
top = [t.id for t in opt.get_top_experiments(3)]
jobs = {tid: params for tid, params in opt.optimizer.get_created_jobs_ids().items()}
opt.stop()

print("RESULT " + json.dumps({"controller_id": controller.id, "jobs": jobs, "top": top}, default=str))
controller.close()
