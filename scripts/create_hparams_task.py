import sys

from clearml import Task

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000

task = Task.create(
    project_name="examples",
    task_name="many hyperparameters (repro)",
    repo="https://github.com/itay-kalininsky/clearml_examples_modified.git",
    branch="main",
    script="pytorch_tensorboardx.py",
    working_directory=".",
    add_task_init_call=False,
)

# Spread across a few sections, mixed value types
sections = ["General", "Model", "Optimizer", "Data"]
params = {}
for i in range(N):
    section = sections[i % len(sections)]
    value = [i, i / 10.0, f"value_{i}", bool(i % 2)][(i // len(sections)) % 4]
    params[f"{section}/hp_{i:05d}"] = value

task.set_parameters(params)
print("Params set:", len(task.get_parameters()))
print("Task ID:", task.id)
print("URL:", task.get_output_log_web_page())
