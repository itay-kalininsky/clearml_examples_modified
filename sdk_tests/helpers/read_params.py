"""Read a task's parameters from a fresh process with Task.get_task.

argv[1]: task id
Prints: RESULT {"raw": ..., "cast": ..., "as_dict": ...}
"""

import json
import sys

from clearml import Task

task = Task.get_task(task_id=sys.argv[1])
print(
    "RESULT "
    + json.dumps(
        {
            "raw": task.get_parameters(),
            "cast": task.get_parameters(cast=True),
            "as_dict": task.get_parameters_as_dict(cast=True),
        }
    )
)
