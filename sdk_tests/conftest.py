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


def pytest_terminal_summary(terminalreporter):
    if not TIMINGS:
        return
    terminalreporter.section("get_by_id timings")
    for t in TIMINGS:
        terminalreporter.write_line(
            f"{t['op']:<14} models={t['models']:<6} median={t['median_s']:.3f}s "
            f"p90={t['p90_s']:.3f}s runs={t['runs']}"
        )


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


def run_script(script, *args, timeout=300):
    """Run a helper script in a fresh process (own Task.init singleton) and return its JSON output.

    The helper must print exactly one line starting with 'RESULT ' followed by JSON.
    """
    proc = subprocess.run(
        [sys.executable, str(HERE / "helpers" / script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(os.environ, SDK_TESTS_PROJECT=PROJECT_NAME),
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    raise AssertionError(
        f"{script} exited {proc.returncode} without a RESULT line\n"
        f"--- stdout ---\n{proc.stdout[-4000:]}\n--- stderr ---\n{proc.stderr[-4000:]}"
    )


def wait_for_status(task, timeout=AGENT_TIMEOUT, interval=2.0):
    """Poll until the task completes or fails. Task.wait_for_status polls every 60s with no timeout."""
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = str(task.get_status())
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
