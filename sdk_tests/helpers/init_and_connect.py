"""Task.init + connect a nested dict and an argparse namespace, in its own process.

argv[1]: JSON of the dict to connect (as section "General")
argv[2]: JSON of argparse defaults {"name": value} (connected as section "Args")
Prints: RESULT {"task_id": ...}
"""

import argparse
import json
import os
import sys

from clearml import Task

params = json.loads(sys.argv[1])
arg_defaults = json.loads(sys.argv[2])

task = Task.init(
    project_name=os.environ.get("SDK_TESTS_PROJECT", "sdk-regression-tests"),
    task_name="test_01_params_roundtrip-init",
    reuse_last_task_id=False,
    auto_connect_arg_parser=False,
    auto_connect_frameworks=False,
    auto_resource_monitoring=False,
)
task.connect(params)  # default section: General

parser = argparse.ArgumentParser()
for name, default in arg_defaults.items():
    if isinstance(default, bool):
        parser.add_argument(f"--{name}", action="store_true", default=default)
    else:
        parser.add_argument(f"--{name}", type=type(default), default=default)
task.connect(parser.parse_args([]), name="Args")

task.flush(wait_for_uploads=True)
task_id = task.id
task.close()
print("RESULT " + json.dumps({"task_id": task_id}))
