"""DAG-21065 B.5 - input and output models on a task."""

from clearml import InputModel, OutputModel, Task
from conftest import PROJECT_NAME, unique_name, unique_uri


def _raw_models(task_id):
    task = Task.get_task(task_id=task_id)
    models = task.data.models
    return (
        [(m.name, m.model) for m in (models.input or [])],
        [(m.name, m.model) for m in (models.output or [])],
    )


def test_input_and_output_models(draft_task, cleanup):
    input_model = InputModel.import_model(
        weights_url=unique_uri(), name=unique_name("in"), project=PROJECT_NAME, framework="PyTorch"
    )
    cleanup.model(input_model)
    input_model.connect(draft_task, name="in_model")

    out_ids = []
    for i in range(2):
        out = OutputModel(task=draft_task, name=f"out_{i}", framework="PyTorch")
        out.update_weights(register_uri=unique_uri(f"out_{i}.pt"), async_enable=False)
        cleanup.model(out.id)
        out_ids.append(out.id)

    draft_task.reload()

    inputs = draft_task.models["input"]
    assert [m.id for m in inputs] == [input_model.id]
    assert list(inputs.keys()) == ["in_model"]

    outputs = draft_task.models["output"]
    assert [m.id for m in outputs] == out_ids  # creation order
    assert list(outputs.keys()) == ["out_0", "out_1"]
    assert outputs[-1].name and outputs[-1].id == out_ids[-1]

    raw_in, raw_out = _raw_models(draft_task.id)
    assert raw_in == [("in_model", input_model.id)]
    assert raw_out == [("out_0", out_ids[0]), ("out_1", out_ids[1])]
    assert draft_task.input_models_id == {"in_model": input_model.id}
    assert draft_task.output_models_id == {"out_0": out_ids[0], "out_1": out_ids[1]}

    draft_task.remove_input_models([input_model.id])
    draft_task.reload()
    assert list(draft_task.models["input"]) == []
    assert [m.id for m in draft_task.models["output"]] == out_ids
    raw_in, raw_out = _raw_models(draft_task.id)
    assert raw_in == []
    assert [mid for _, mid in raw_out] == out_ids
