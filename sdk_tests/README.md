# ClearML SDK regression suite (DAG-21065)

Automates section B of the DAG-21065 test plan ("Faster task loading for tasks with many models or
hyperparameters") against a live ClearML server. For the full setup, including the venv, agent,
Zabbix CPU and old vs new comparison, see the [repo README](../README.md).

| File | Plan item | Needs |
|---|---|---|
| `test_01_params_roundtrip.py` | 1. Parameters round trip | server |
| `test_02_params_api_edit.py` | 2. Parameters edited through the API | server |
| `test_03_single_param_edit.py` | 3. Single parameter edits (no `_cls`) | server |
| `test_04_user_properties.py` | 4. User properties | server |
| `test_05_models.py` | 5. Input and output models | server |
| `test_06_many_models.py` | 6. ~2,000 output models: timings, load phase, order, last item | server (`slow`) |
| `test_07_clone_enqueue.py` | 7. Clone and enqueue | agent |
| `test_08_pipeline.py` | 8. Pipeline, `${step1.models.output.-1.url}` | agent |
| `test_09_hpo.py` | 9. HPO, RandomSearch | agent |

Supporting files:
- `conftest.py`: server and agent checks, fixtures, cleanup, run record.
- `helpers/`: scripts run in a subprocess, because `Task.init` is a per-process singleton.
- `agent_scripts/`: scripts the agent runs for items 7 and 9.

## Running

From this directory, with the repo venv (`../.venv`, created from `requirements-test.txt`):

```bash
../.venv/bin/python -m pytest -v                            # everything
../.venv/bin/python -m pytest -m "not agent and not slow"    # items 1-5
../.venv/bin/python -m pytest -m slow                        # item 6
../.venv/bin/python -m pytest -m agent                       # items 7-9
../.venv/bin/python -m pytest test_04_user_properties.py     # a single file
```

The server is whatever the ClearML SDK is configured for: `CLEARML_CONFIG_FILE`, or
`CLEARML_API_HOST` / `CLEARML_API_ACCESS_KEY` / `CLEARML_API_SECRET_KEY`.

- All tests are skipped with a clear reason if the server isn't reachable.
- Agent tests are skipped if no worker listens on the queue when the run starts.
- An agent test fails after `SDK_TESTS_NO_WORKER_GRACE` seconds if its task is queued and the worker has disappeared.

## Outputs

`results/` is git-ignored.
- `timings-<host>.json`: item 6 `reload()` / `Task.get_task` samples (median and p90). Each run overwrites it.
- `run-<host>-<utc time>.json`: one file per pytest run, containing:
  - the server version
  - each test's `start_unix`, `end_unix` and outcome
  - the item 6 timings
  - the load phase result: clients, requests, errors, req/s, p50/p90/p99 latency, and its time window

Use the time windows to read server CPU from Zabbix (`apiserver.cpu.usage` on `customer-itay-enterprise-server`, 60 s samples).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SDK_TESTS_PROJECT` | `sdk-regression-tests` | project for all test tasks |
| `SDK_TESTS_QUEUE` | `default` | queue for agent tests |
| `SDK_TESTS_AGENT_TIMEOUT` | `900` | seconds to wait for agent tasks |
| `SDK_TESTS_NO_WORKER_GRACE` | `120` | fail an agent test when its task is queued with no worker for this long |
| `SDK_TESTS_MANY_MODELS` | `2000` | output models in item 6 |
| `SDK_TESTS_TIMING_RUNS` | `5` | timed repetitions in item 6 |
| `SDK_TESTS_MAX_RELOAD_SEC` | unset | fail item 6 if the median reload/get_task exceeds it |
| `SDK_TESTS_LOAD_CLIENTS` | `4` | concurrent `get_by_id` callers in the item 6 load phase (`0` skips it) |
| `SDK_TESTS_LOAD_SECONDS` | `180` | load phase duration (3 Zabbix samples) |
| `SDK_TESTS_REPO` / `SDK_TESTS_REPO_BRANCH` | this repo / `main` | where the agent gets `agent_scripts/` |
| `SDK_TESTS_KEEP` | unset | keep created tasks and models for inspection |

Teardown deletes all tasks and models a test creates, unless `SDK_TESTS_KEEP` is set.
Pipeline and HPO runs are tagged per test, so they're cleaned up even if a helper times out.
