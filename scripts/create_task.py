from clearml import Task

task = Task.create(
    project_name="examples",
    task_name="torch.save every epoch (repro)",
    repo="https://github.com/itay-kalininsky/clearml_examples_modified.git",
    branch="main",
    script="pytorch_tensorboardx.py",
    working_directory=".",
    add_task_init_call=False,  # the script already calls Task.init
)
print("Task ID:", task.id)
print("URL:", task.get_output_log_web_page())
