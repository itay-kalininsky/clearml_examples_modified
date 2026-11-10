# clearml_examples_modified

Modified ClearML example used to reproduce a task being populated with thousands of output models.

`pytorch_tensorboardx.py` is based on `examples/frameworks/pytorch/pytorch_tensorboardx.py`, with these changes:

- `torch.save(model, .../model{epoch})` runs after every epoch (unique file per epoch), so each save is registered as an output model.
- Training uses a small MNIST subset (`--train-samples`, default 128) so epochs are fast.
- `--epochs` defaults to 1000.
- `--output-uri` is passed to `Task.init` to optionally upload each saved model.

```
pip install -r requirements.txt
python pytorch_tensorboardx.py --epochs 2000 --no-cuda [--output-uri <uri>]
```
