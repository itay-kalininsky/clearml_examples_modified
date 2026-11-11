"""DAG-21065 B.4 - user properties."""

from clearml import Task


def test_user_properties(draft_task):
    draft_task.set_user_properties(a=1, b={"value": 2, "description": "d"})
    draft_task.reload()

    props = draft_task.get_user_properties()
    assert set(props) == {"a", "b"}
    assert props["a"]["value"] == "1"
    assert props["a"]["section"] == "properties"
    assert props["b"]["value"] == "2"
    assert props["b"]["description"] == "d"

    assert draft_task.get_user_properties(value_only=True) == {"a": "1", "b": "2"}

    # Same result from a fresh object (goes through tasks.get_by_id).
    fresh = Task.get_task(task_id=draft_task.id)
    assert fresh.get_user_properties(value_only=True) == {"a": "1", "b": "2"}
