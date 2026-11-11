"""Executed by clearml-agent in test_07: reports the parameters it actually received."""

from clearml import Task

task = Task.init(project_name="sdk-regression-tests", task_name="echo_params")
params = task.connect({"lr": 0.1, "name": "base"})

task.get_logger().report_scalar("params", "lr", value=float(params["lr"]), iteration=0)
print(f"name={params['name']}")
task.flush(wait_for_uploads=True)
