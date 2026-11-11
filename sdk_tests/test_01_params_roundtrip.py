"""DAG-21065 B.1 - parameters round trip (Task.init + connect, then reload / get_task)."""

import json

import pytest

from clearml import Task
from conftest import run_script

CONNECTED = {
    "i": 3,
    "f": 0.5,
    "b": True,
    "s": "hello",
    "n": None,
    "l": [1, 2, "x"],
    "nested": {"a": 1, "deep": {"z": False}},
}
ARG_DEFAULTS = {"lr": 0.01, "name": "nm", "epochs": 7, "flag": False}

# Flat "Section/key" view of what was connected.
EXPECTED_CAST = {
    "General/i": 3,
    "General/f": 0.5,
    "General/b": True,
    "General/s": "hello",
    "General/n": None,
    "General/l": [1, 2, "x"],
    "General/nested/a": 1,
    "General/nested/deep/z": False,
    "Args/lr": 0.01,
    "Args/name": "nm",
    "Args/epochs": 7,
    "Args/flag": False,
}
# Stored (uncast) string form. None is stored as "" and lists as JSON.
EXPECTED_RAW = {
    "General/i": "3",
    "General/f": "0.5",
    "General/b": "True",
    "General/s": "hello",
    "General/n": "",
    "General/l": '[1, 2, "x"]',
    "General/nested/a": "1",
    "General/nested/deep/z": "False",
    "Args/lr": "0.01",
    "Args/name": "nm",
    "Args/epochs": "7",
    "Args/flag": "False",
}
EXPECTED_DICT = {"General": CONNECTED, "Args": ARG_DEFAULTS}


@pytest.fixture(scope="module")
def connected_task_id():
    result = run_script("init_and_connect.py", json.dumps(CONNECTED), json.dumps(ARG_DEFAULTS))
    task_id = result["task_id"]
    yield task_id
    Task.get_task(task_id=task_id).delete(raise_on_error=False)


@pytest.fixture(scope="module")
def reloaded(connected_task_id):
    task = Task.get_task(task_id=connected_task_id)
    task.reload()
    return task


@pytest.mark.parametrize("key", sorted(EXPECTED_CAST))
def test_cast_value_and_type(reloaded, key):
    value = reloaded.get_parameters(cast=True)[key]
    assert value == EXPECTED_CAST[key]
    assert type(value) is type(EXPECTED_CAST[key])


def test_raw_values(reloaded):
    assert reloaded.get_parameters() == EXPECTED_RAW


def test_as_dict(reloaded):
    assert reloaded.get_parameters_as_dict(cast=True) == EXPECTED_DICT


def test_fresh_process_get_task(connected_task_id):
    result = run_script("read_params.py", connected_task_id)
    assert result["raw"] == EXPECTED_RAW
    assert result["cast"] == EXPECTED_CAST
    assert result["as_dict"] == EXPECTED_DICT
