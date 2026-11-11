# ClearML SDK regression suite (DAG-21065)

Automates section B of the DAG-21065 test plan ("Faster task loading for tasks with many models or
hyperparameters") against a live ClearML server.

| File | Plan item | Needs |
|---|---|---|
| `test_01_params_roundtrip.py` | 1. Parameters round trip | server |
| `test_02_params_api_edit.py` | 2. Parameters edited through the API | server |
| `test_03_single_param_edit.py` | 3. Single parameter edits (no `_cls`) | server |
| `test_04_user_properties.py` | 4. User properties | server |
| `test_05_models.py` | 5. Input and output models | server |
| `test_06_many_models.py` | 6. ~2,000 output models + timings | server (`slow`) |
| `test_07_clone_enqueue.py` | 7. Clone and enqueue | agent |
| `test_08_pipeline.py` | 8. Pipeline, `${step1.models.output.-1.url}` | agent |
| `test_09_hpo.py` | 9. HPO, RandomSearch | agent |

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt
```

The server is whatever the ClearML SDK is configured for: `CLEARML_CONFIG_FILE`, or
`CLEARML_API_HOST` / `CLEARML_API_ACCESS_KEY` / `CLEARML_API_SECRET_KEY`.

## Running

```bash
cd sdk_tests
pytest -m "not agent and not slow"     # items 1-5, a few minutes
pytest -m slow                         # item 6
pytest -m agent                        # items 7-9, needs a clearml-agent on the queue
pytest                                 # everything
```

Agent tests are skipped automatically when no worker listens on the queue.
The agent clones this repo (`SDK_TESTS_REPO`, branch `SDK_TESTS_REPO_BRANCH`) to run
`agent_scripts/*.py`, so the version you test must be pushed.

### Old vs new server

Run once per server and diff the timing files:

```bash
CLEARML_CONFIG_FILE=~/clearml-old.conf pytest
CLEARML_CONFIG_FILE=~/clearml-new.conf pytest
diff results/timings-<old-host>.json results/timings-<new-host>.json
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SDK_TESTS_PROJECT` | `sdk-regression-tests` | project for all test tasks |
| `SDK_TESTS_QUEUE` | `default` | queue for agent tests |
| `SDK_TESTS_AGENT_TIMEOUT` | `900` | seconds to wait for agent tasks |
| `SDK_TESTS_MANY_MODELS` | `2000` | output models in item 6 |
| `SDK_TESTS_TIMING_RUNS` | `5` | timed repetitions in item 6 |
| `SDK_TESTS_MAX_RELOAD_SEC` | unset | fail item 6 if the median reload/get_task exceeds it |
| `SDK_TESTS_REPO` / `SDK_TESTS_REPO_BRANCH` | this repo / `main` | where the agent gets `agent_scripts/` |
| `SDK_TESTS_KEEP` | unset | keep created tasks and models for inspection |

All tasks and models a test creates are deleted in teardown unless `SDK_TESTS_KEEP` is set.
