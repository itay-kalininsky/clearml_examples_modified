"""Base task for test_09 (HPO): objective = x * (2 if y == "b" else 1)."""

from clearml import Task

task = Task.init(project_name="sdk-regression-tests", task_name="hpo_base")
params = task.connect({"x": 1, "y": "a"})

x = int(params["x"])
objective = x * (2 if params["y"] == "b" else 1)
task.get_logger().report_scalar("objective", "value", value=objective, iteration=0)
print(f"x={x} y={params['y']} objective={objective}")
task.flush(wait_for_uploads=True)
