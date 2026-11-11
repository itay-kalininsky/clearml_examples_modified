"""DAG-21065 B.3 - single parameter edits leave no extra fields (e.g. _cls)."""

from clearml import Task
from clearml.backend_api.services import tasks as tasks_api

ITEM_FIELDS = {"section", "name", "value", "type", "description"}


def _assert_clean(task_id, expected_params):
    task = Task.get_task(task_id=task_id)
    params = task.get_parameters()
    assert params == expected_params
    assert not [k for k in params if "_cls" in k]
    for section, items in task.data.hyperparams.items():
        for name, item in items.items():
            fields = set(item.to_dict())
            assert fields <= ITEM_FIELDS, f"{section}/{name} has extra fields {fields - ITEM_FIELDS}"
    # Also check the raw JSON the server returns, which bypasses the SDK's typed models.
    resp = task.session.send_request("tasks", "get_by_id", json={"task": task_id}, method="post")
    assert resp.status_code == 200, resp.text
    raw = resp.json()["data"]["task"].get("hyperparams", {})
    for section, items in raw.items():
        assert "_cls" not in items, section
        for name, item in items.items():
            assert set(item) <= ITEM_FIELDS, f"raw {section}/{name}: {sorted(item)}"


def test_set_parameter(draft_task):
    draft_task.set_parameter("Args/x", 1)
    _assert_clean(draft_task.id, {"Args/x": "1"})

    draft_task.set_parameter("Args/y", "two", description="second")
    _assert_clean(draft_task.id, {"Args/x": "1", "Args/y": "two"})


def test_edit_hyper_params_single(draft_task):
    """The UI edits one parameter through tasks.edit_hyper_params."""
    draft_task.set_parameter("Args/x", 1)
    draft_task.session.send(
        tasks_api.EditHyperParamsRequest(
            task=draft_task.id,
            hyperparams=[tasks_api.ParamsItem(section="Args", name="x", value="42", type="int", description="ui")],
            replace_hyperparams="none",
        )
    )
    _assert_clean(draft_task.id, {"Args/x": "42"})
    item = Task.get_task(task_id=draft_task.id).data.hyperparams["Args"]["x"]
    assert (item.type, item.description) == ("int", "ui")
