"""DAG-21065 B.2 - parameters edited through the raw tasks.edit API."""

import itertools

import pytest

from clearml import Task

FIELDS = ("section", "name", "value", "type", "description")
# A spread of key orders (the typed request classes always serialize in one order, so we send raw JSON).
ORDERS = [p for i, p in enumerate(itertools.permutations(FIELDS)) if i % 23 == 0]

PARAMS = {
    "x": {"value": "3", "type": "int", "description": "desc x", "expected": 3},
    "y": {"value": "1.5", "type": "float", "description": "desc y", "expected": 1.5},
    "flag": {"value": "True", "type": "bool", "description": "desc flag", "expected": True},
    "z": {"value": "hello", "type": None, "description": "desc z (type null)", "expected": "hello"},
}


def _item(name, spec, order):
    full = {"section": "Args", "name": name, "value": spec["value"], "type": spec["type"],
            "description": spec["description"]}
    return {k: full[k] for k in order}


def _raw_edit(task, hyperparams):
    resp = task.session.send_request(
        "tasks", "edit", json={"task": task.id, "hyperparams": hyperparams}, method="post"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["updated"] == 1, resp.text


@pytest.fixture(params=ORDERS, ids=lambda o: "-".join(k[:2] for k in o))
def edited_task(request, draft_task):
    order = request.param
    # Rotate the order per parameter too, so items within one request differ.
    hp = {"Args": {name: _item(name, spec, order[i:] + order[:i]) for i, (name, spec) in enumerate(PARAMS.items())}}
    _raw_edit(draft_task, hp)
    return draft_task


def test_get_task_cast_values(edited_task, clearml_log):
    task = Task.get_task(task_id=edited_task.id)
    cast = task.get_parameters(cast=True)
    assert cast == {f"Args/{n}": s["expected"] for n, s in PARAMS.items()}
    assert not [m for m in clearml_log if "Failed reloading" in m]


def test_stored_type_and_description(edited_task):
    stored = Task.get_task(task_id=edited_task.id).data.hyperparams["Args"]
    for name, spec in PARAMS.items():
        assert stored[name].type == spec["type"], name
        assert stored[name].description == spec["description"], name


def test_set_parameters_keeps_type_and_description(edited_task, clearml_log):
    task = Task.get_task(task_id=edited_task.id)
    task.set_parameters({"Args/x": 5})

    stored = Task.get_task(task_id=edited_task.id).data.hyperparams["Args"]
    assert stored["x"].value == "5"
    assert stored["x"].type == "int"
    assert stored["x"].description == "desc x"
    # set_parameters replaces the whole parameter set (update_parameters merges).
    assert set(stored) == {"x"}
    assert not [m for m in clearml_log if "Failed reloading" in m]
