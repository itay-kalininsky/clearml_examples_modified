# clearml_examples_modified

Everything for reproducing and verifying the Odin `tasks.get_by_id` issue (DEVOPS-5680 / QA ticket DAG-21065): a task flooded with output models, a task with many hyperparameters, and an automated SDK regression suite.

```
clearml_examples_modified/
├── .venv/                       local virtualenv (git-ignored, see Setup)
├── pytorch_tensorboardx.py      repro: torch.save every epoch -> one output model per epoch
├── requirements.txt             deps for pytorch_tensorboardx.py (torch, torchvision, tensorboardX, ...)
├── scripts/
│   ├── create_task.py           draft task that runs pytorch_tensorboardx.py from this repo
│   └── create_hparams_task.py   draft task with N hyperparameters
└── sdk_tests/                   DAG-21065 regression suite (items 1-9), see sdk_tests/README.md
    └── results/                 timing files and run records (git-ignored)
```

## Run everything: quick start

### 1. Setup (once)

```bash
cd ~/Documents/projects/clearml/clearml_examples_modified
python3 -m venv .venv
.venv/bin/pip install -r sdk_tests/requirements-test.txt   # clearml==2.2.0, pytest==9.2.0
# only needed to run the repro example locally (large: torch):
# .venv/bin/pip install -r requirements.txt
```

### 2. Point the SDK at a server

The suite and the scripts use the normal ClearML SDK config. Keep one conf file per server:

```bash
export CLEARML_CONFIG_FILE=~/clearml.conf        # currently app.itay.hosted.clearml.io
```

### 3. Start an agent (items 7-9 only)

On the agent machine, run it so it survives the SSH session ending:

```bash
clearml-agent daemon --queue default --detached     # stop: clearml-agent daemon --queue default --stop
```

The agent clones this repo from GitHub to run `sdk_tests/agent_scripts/`, so push before testing changes to those scripts.

### 4. Run the suite

Always run from `sdk_tests/`. Running from inside the SDK checkout would import the local `clearml/` source instead of the pinned package.

```bash
cd sdk_tests
../.venv/bin/python -m pytest -v                                # everything, about 30 min
../.venv/bin/python -m pytest -m "not agent and not slow"        # items 1-5, about 5 min
../.venv/bin/python -m pytest -m slow                            # item 6: 2,000 models, timings, 3 min load phase
../.venv/bin/python -m pytest -m agent                           # items 7-9, needs step 3
```

At the end, pytest prints the `get_by_id` timings, the load phase result and the path of the run record (`results/run-<host>-<time>.json`). The run record holds every test's start and end time, used for matching server CPU.

### 5. Server CPU (Zabbix)

The suite can't read server CPU itself. Zabbix collects it every 60 s on host `customer-itay-enterprise-server`:

- `apiserver.cpu.usage`: apiserver container, 100% = 1 core. This is the main number.
- `mongodb.cpu.usage`, `elastic.cpu.usage`: the other containers.
- `system.cpu.util`: whole host (4 CPUs).

Take `start_unix` and `end_unix` of the load phase (`load` in the run record) or of any test (`tests`), then open Zabbix → Monitoring → Latest data → the item → Graph for that window. You can also ask Claude Code to pull it with the Zabbix MCP.

### 6. Old vs new server

Run the identical client against both builds and compare:

```bash
cd sdk_tests
CLEARML_CONFIG_FILE=~/clearml-old.conf ../.venv/bin/python -m pytest -m slow
CLEARML_CONFIG_FILE=~/clearml-new.conf ../.venv/bin/python -m pytest -m slow
ls results/        # timings-<host>.json and run-<host>-<time>.json for each server
```

Compare the load phase `req_per_s` and latency, the `reload()` / `get_task` medians, and Zabbix `apiserver.cpu.usage` during each load window. For the customer's scale, add `SDK_TESTS_MANY_MODELS=7500`.

## Repro example and scripts

`pytorch_tensorboardx.py` is based on the SDK's `examples/frameworks/pytorch/pytorch_tensorboardx.py`:

- `torch.save(model, .../model{epoch})` runs after every epoch, with a unique file per epoch, so each save is registered as an output model.
- Training uses a small MNIST subset (`--train-samples`, default 128) so epochs are fast.
- `--epochs` defaults to 1000.
- `--output-uri` is passed to `Task.init` to optionally upload each saved model.

```bash
.venv/bin/python pytorch_tensorboardx.py --epochs 2000 --no-cuda [--output-uri <uri>]
```

Draft tasks on the configured server, which you then enqueue from the UI:

```bash
.venv/bin/python scripts/create_task.py             # runs pytorch_tensorboardx.py from this repo
.venv/bin/python scripts/create_hparams_task.py 2000  # task with 2000 hyperparameters
```
