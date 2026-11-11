"""DAG-21065 B.6 - a task with thousands of output models (the original client problem).

SDK_TESTS_MANY_MODELS   number of output models (default 2000)
SDK_TESTS_TIMING_RUNS   timed repetitions per operation (default 5)
SDK_TESTS_MAX_RELOAD_SEC  if set, fail when the median reload()/get_task() time exceeds it
"""

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest

from clearml import Task
from clearml.backend_api import Session
from clearml.backend_api.services import models as models_api
from clearml.backend_api.services import tasks as tasks_api
from conftest import HERE, PROJECT_NAME, TIMINGS, delete_models, delete_task, unique_name, unique_uri

pytestmark = pytest.mark.slow

N = int(os.environ.get("SDK_TESTS_MANY_MODELS", "2000"))
RUNS = int(os.environ.get("SDK_TESTS_TIMING_RUNS", "5"))
MAX_SEC = os.environ.get("SDK_TESTS_MAX_RELOAD_SEC")


def _name(i):
    return f"model_{i:05d}"


def _created_times(model_ids):
    """{model_id: created} straight from the server."""
    session = Task._get_default_session()
    created = {}
    for i in range(0, len(model_ids), 500):
        resp = session.send(
            models_api.GetAllRequest(id=model_ids[i:i + 500], only_fields=["id", "created"], page_size=500)
        )
        created.update((m.id, m.created) for m in resp.response.models)
    return created


@pytest.fixture(scope="module")
def many_models_task():
    task = Task.create(project_name=PROJECT_NAME, task_name=unique_name("test_06_many_models"))
    session = task.session
    project_id = task.project

    def create(i):
        resp = session.send(
            models_api.CreateRequest(
                uri=unique_uri(f"checkpoint_{i}.pt"), name=f"many-{i}", task=task.id, project=project_id
            )
        )
        return resp.response.id

    model_ids = []
    try:
        # Created from a thread pool for speed, so creation order differs from submit order.
        # Like a real run (one torch.save -> one model linked right away), link them in creation
        # order: model_00000 is the oldest model, model_{N-1} the newest.
        with ThreadPoolExecutor(max_workers=8) as pool:
            model_ids = list(pool.map(create, range(N)))
        created = _created_times(model_ids)
        model_ids.sort(key=lambda mid: (created[mid], mid))
        session.send(
            tasks_api.EditRequest(
                task=task.id,
                models=tasks_api.TaskModels(
                    input=[],
                    output=[tasks_api.TaskModelItem(name=_name(i), model=mid) for i, mid in enumerate(model_ids)],
                ),
            )
        )
        yield task.id, model_ids
    finally:
        if not os.environ.get("SDK_TESTS_KEEP"):
            delete_models(model_ids)
            delete_task(task.id)


def _time(op, fn):
    samples = []
    for _ in range(RUNS):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    samples.sort()
    result = {
        "op": op,
        "models": N,
        "runs": RUNS,
        "median_s": statistics.median(samples),
        "p90_s": samples[min(len(samples) - 1, int(round(0.9 * (len(samples) - 1))))],
        "samples_s": samples,
    }
    TIMINGS.append(result)
    return result


def test_timings(many_models_task):
    task_id, _ = many_models_task
    task = Task.get_task(task_id=task_id)
    results = [
        _time("reload()", task.reload),
        _time("Task.get_task", lambda: Task.get_task(task_id=task_id)),
    ]

    host = urlparse(Session.get_api_server_host()).hostname or "unknown"
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"timings-{host}.json"
    out.write_text(
        json.dumps(
            {
                "api_host": Session.get_api_server_host(),
                "server_version": Session.server_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "results": results,
            },
            indent=2,
        )
    )

    if MAX_SEC:
        for r in results:
            assert r["median_s"] <= float(MAX_SEC), f"{r['op']} median {r['median_s']:.3f}s > {MAX_SEC}s"


def test_output_models_count_order_last(many_models_task):
    task_id, model_ids = many_models_task
    task = Task.get_task(task_id=task_id)
    task.reload()
    outputs = task.models["output"]

    assert len(outputs) == N
    assert {m.id for m in outputs} == set(model_ids)
    # Each model is listed under the name the task links it with.
    assert all(m.name == _name(model_ids.index(m.id)) for m in outputs)

    # Order: oldest first. The SDK takes the first page of models.get_all(order_by=created)
    # (the server's default page is 500, see clearml/backend_interface/task/models.py:107) and
    # appends the rest in task-link order, which here is also creation order. Models created in
    # the same millisecond may swap, so compare creation times, not ids.
    created = _created_times(model_ids)
    times = [created[m.id] for m in outputs]
    assert times == sorted(times)

    # Last item: the newest model.
    assert created[outputs[-1].id] == max(created.values())
    if N > 500:
        # Past the first page the tail comes from link order, so the last item is exact.
        assert outputs[-1].name == _name(N - 1)
    # The task-level links keep the order they were written in.
    assert [m.name for m in task.data.models.output] == [_name(i) for i in range(N)]


def test_set_parameters_still_works(many_models_task, clearml_log):
    task_id, _ = many_models_task
    task = Task.get_task(task_id=task_id)
    task.set_parameters({"Args/x": 5})
    assert Task.get_task(task_id=task_id).get_parameters(cast=True) == {"Args/x": 5}
    assert len(Task.get_task(task_id=task_id).data.models.output) == N
    assert not [m for m in clearml_log if "Failed reloading" in m]
