"""Shared fixtures for the ClearML SDK regression suite (DAG-21065).

The server is whatever the ClearML SDK is configured for: CLEARML_CONFIG_FILE,
or CLEARML_API_HOST / CLEARML_API_ACCESS_KEY / CLEARML_API_SECRET_KEY.
"""

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from clearml import Task
from clearml.backend_api import Session
from clearml.backend_api.session.client import APIClient

HERE = Path(__file__).resolve().parent
PROJECT_NAME = os.environ.get("SDK_TESTS_PROJECT", "sdk-regression-tests")
QUEUE_NAME = os.environ.get("SDK_TESTS_QUEUE", "default")
AGENT_TIMEOUT = float(os.environ.get("SDK_TESTS_AGENT_TIMEOUT", "900"))
REPO_URL = os.environ.get("SDK_TESTS_REPO", "https://github.com/itay-kalininsky/clearml_examples_modified.git")
REPO_BRANCH = os.environ.get("SDK_TESTS_REPO_BRANCH", "main")

_server_error = None
_agent_error = None


def _check_server():
    client = APIClient()
    client.projects.get_all(page_size=1)
    return client


def _check_agent(client):
    queues = [q for q in client.queues.get_all(name=f"^{QUEUE_NAME}$")]
    if not queues:
        return f"queue '{QUEUE_NAME}' does not exist"
    qid = queues[0].id
    for w in client.workers.get_all():
        if any(q.id == qid for q in (w.queues or [])):
            return None
    return f"no worker is listening on queue '{QUEUE_NAME}'"


def pytest_configure(config):
    global _server_error, _agent_error
    try:
        client = _check_server()
        _agent_error = _check_agent(client)
    except Exception as ex:  # noqa: BLE001 - any failure means "server unusable"
        _server_error = f"ClearML server not reachable: {ex}"


def pytest_report_header(config):
    if _server_error:
        return [_server_error]
    return [
        f"clearml api host: {Session.get_api_server_host()}",
        f"clearml server version: {Session.server_version}  api: {Session.api_version}",
        f"test project: {PROJECT_NAME}  queue: {QUEUE_NAME}"
        + (f"  (agent tests skipped: {_agent_error})" if _agent_error else ""),
    ]


TIMINGS = []  # filled by test_06, printed in the terminal summary
LOAD_RESULTS = []  # filled by test_06's load phase
_test_windows = []  # (nodeid, start_unix, end_unix, outcome) for matching server CPU (Zabbix) afterwards
_session_start = time.time()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    start = time.time()
    outcomes = []
    item._sdk_outcomes = outcomes
    yield
    _test_windows.append(
        {
            "test": item.nodeid,
            "start_unix": int(start),
            "end_unix": int(time.time()),
            "outcome": "failed" if "failed" in outcomes else ("skipped" if outcomes == ["skipped"] else "passed"),
        }
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if hasattr(item, "_sdk_outcomes") and (report.when == "call" or report.outcome != "passed"):
        item._sdk_outcomes.append(report.outcome)


def _write_run_record():
    """results/run-<host>-<utc time>.json: test time windows, timings and load results."""
    from datetime import datetime, timezone
    from urllib.parse import urlparse

    if _server_error:
        return None
    host = urlparse(Session.get_api_server_host()).hostname or "unknown"
    stamp = datetime.fromtimestamp(_session_start, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"run-{host}-{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "api_host": Session.get_api_server_host(),
                "server_version": Session.server_version,
                "session_start_unix": int(_session_start),
                "session_end_unix": int(time.time()),
                "tests": _test_windows,
                "timings": TIMINGS,
                "load": LOAD_RESULTS,
            },
            indent=2,
        )
    )
    return out


def pytest_terminal_summary(terminalreporter):
    record = _write_run_record()
    if TIMINGS:
        terminalreporter.section("get_by_id timings")
        for t in TIMINGS:
            terminalreporter.write_line(
                f"{t['op']:<14} models={t['models']:<6} median={t['median_s']:.3f}s "
                f"p90={t['p90_s']:.3f}s runs={t['runs']}"
            )
    for r in LOAD_RESULTS:
        terminalreporter.section("get_by_id load phase")
        terminalreporter.write_line(
            f"models={r['models']} clients={r['clients']} duration={r['duration_s']:.0f}s "
            f"requests={r['requests']} errors={r['errors']} rate={r['req_per_s']:.1f} req/s "
            f"p50={r['p50_ms']:.0f}ms p90={r['p90_ms']:.0f}ms p99={r['p99_ms']:.0f}ms "
            f"window={r['start_unix']}..{r['end_unix']}"
        )
    if record:
        terminalreporter.write_line(f"run record (test windows for Zabbix CPU): {record}")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if _server_error:
            item.add_marker(pytest.mark.skip(reason=_server_error))
        elif _agent_error and "agent" in item.keywords:
            item.add_marker(pytest.mark.skip(reason=f"agent tests skipped: {_agent_error}"))


# ---------------------------------------------------------------- helpers


def unique_name(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def unique_uri(filename="model.pt"):
    """A never-fetched, never-reused model URI.

    InputModel.import_model() returns an existing model when the URI is already
    registered, so every model in the suite gets a fresh one.
    """
    return f"https://example.invalid/sdk-tests/{uuid.uuid4().hex}/{filename}"


def run_script(script, *args, timeout=300, run_tag=None):
    """Run a helper script in a fresh process (own Task.init singleton) and return its JSON output.

    The helper must print exactly one line starting with 'RESULT ' followed by JSON.
    run_tag is passed as SDK_TESTS_RUN_TAG so helpers can tag what they create.
    """
    env = dict(os.environ, SDK_TESTS_PROJECT=PROJECT_NAME)
    if run_tag:
        env["SDK_TESTS_RUN_TAG"] = run_tag
    try:
        proc = subprocess.run(
            [sys.executable, str(HERE / "helpers" / script), *map(str, args)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as ex:
        out = ex.stdout.decode(errors="replace") if isinstance(ex.stdout, bytes) else (ex.stdout or "")
        raise AssertionError(f"{script} timed out after {timeout:.0f}s\n--- stdout tail ---\n{out[-4000:]}")
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    raise AssertionError(
        f"{script} exited {proc.returncode} without a RESULT line\n"
        f"--- stdout ---\n{proc.stdout[-4000:]}\n--- stderr ---\n{proc.stderr[-4000:]}"
    )


NO_WORKER_GRACE = float(os.environ.get("SDK_TESTS_NO_WORKER_GRACE", "120"))


def worker_problem():
    """None if a worker listens on QUEUE_NAME, else a reason string."""
    try:
        return _check_agent(APIClient())
    except Exception as ex:  # noqa: BLE001
        return f"could not check workers: {ex}"


def wait_for_status(task, timeout=AGENT_TIMEOUT, interval=2.0):
    """Poll until the task completes or fails. Task.wait_for_status polls every 60s with no timeout.

    Fails early if the task stays queued while no worker listens on the queue for NO_WORKER_GRACE
    seconds (e.g. the agent died with its SSH session).
    """
    deadline = time.monotonic() + timeout
    status = None
    no_worker_since = None
    while time.monotonic() < deadline:
        status = str(task.get_status())
        if status == "queued":
            problem = worker_problem()
            if problem is None:
                no_worker_since = None
            else:
                no_worker_since = no_worker_since or time.monotonic()
                if time.monotonic() - no_worker_since > NO_WORKER_GRACE:
                    raise AssertionError(f"task {task.id} is queued but {problem} (for {NO_WORKER_GRACE:.0f}s)")
        if status in ("completed", "closed", "published"):
            return status
        if status in ("failed", "stopped"):
            raise AssertionError(
                f"task {task.id} ended with status '{status}'. Console tail:\n"
                + "\n".join(str(r) for r in (task.get_reported_console_output(number_of_reports=3) or []))[-4000:]
            )
        time.sleep(interval)
    raise AssertionError(f"task {task.id} still '{status}' after {timeout:.0f}s")


def delete_models(model_ids, chunk=500):
    from clearml.backend_api.services import models as models_api

    session = Task._get_default_session()
    ids = list(model_ids)
    for i in range(0, len(ids), chunk):
        try:
            session.send(models_api.DeleteManyRequest(ids=ids[i:i + chunk], force=True))
        except Exception as ex:  # noqa: BLE001 - cleanup must not fail the test
            logging.getLogger(__name__).warning("model cleanup failed: %s", ex)


def delete_tagged(tag):
    """Delete every task carrying `tag`, their direct children (pipeline steps, HPO jobs) and
    the models those tasks created. Used so cleanup works even when a helper never returned ids."""
    client = APIClient()
    tagged = [t.id for t in client.tasks.get_all(tags=[tag], search_hidden=True, only_fields=["id"])]
    if not tagged:
        return
    children = [t.id for t in client.tasks.get_all(parent=tagged, search_hidden=True, only_fields=["id"])]
    task_ids = list(dict.fromkeys(children + tagged))
    model_ids = [m.id for m in client.models.get_all(task=task_ids, only_fields=["id"])]
    delete_models(model_ids)
    for tid in task_ids:
        try:
            Task.dequeue(tid)
        except Exception:  # noqa: BLE001 - not queued
            pass
        delete_task(tid)


def delete_task(task):
    try:
        Task.get_task(task_id=task.id if isinstance(task, Task) else task).delete(
            delete_artifacts_and_models=False, raise_on_error=False
        )
    except Exception as ex:  # noqa: BLE001
        logging.getLogger(__name__).warning("task cleanup failed: %s", ex)


# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def project_name():
    return PROJECT_NAME


@pytest.fixture(scope="session")
def queue_name():
    return QUEUE_NAME


@pytest.fixture
def cleanup():
    """Register task ids / model ids for deletion in teardown (models first)."""

    class Cleanup:
        def __init__(self):
            self.tasks, self.models = [], []
            # Pass to run_script(run_tag=...) / add to tasks; everything tagged is swept in teardown.
            self.tag = unique_name("sdk-tests-run")

        def task(self, t):
            self.tasks.append(t.id if isinstance(t, Task) else t)
            return t

        def model(self, m):
            self.models.append(getattr(m, "id", m))
            return m

    c = Cleanup()
    yield c
    if os.environ.get("SDK_TESTS_KEEP"):
        return
    delete_models(c.models)
    for tid in reversed(c.tasks):
        delete_task(tid)
    try:
        delete_tagged(c.tag)
    except Exception as ex:  # noqa: BLE001
        logging.getLogger(__name__).warning("tag cleanup failed: %s", ex)


@pytest.fixture
def draft_task(request, cleanup):
    task = Task.create(project_name=PROJECT_NAME, task_name=unique_name(request.node.name[:60]))
    cleanup.task(task)
    return task


@pytest.fixture
def clearml_log():
    """Collect messages logged by the SDK on the 'clearml' logger (it does not reliably reach caplog)."""
    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = _Collector(level=logging.DEBUG)
    logger = logging.getLogger("clearml")
    logger.addHandler(handler)
    yield records
    logger.removeHandler(handler)
