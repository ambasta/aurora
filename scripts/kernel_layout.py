"""Generate host metadata from the numeric tables compiled into the kernel."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def read_table(path):
    values = {}
    for statement in ast.parse(path.read_text()).body:
        name, *arguments = statement.value.args
        values[name.id] = tuple(ast.literal_eval(argument) for argument in arguments)
    return values


def metadata():
    return {name: values[0] for name, values in read_table(ROOT / "kernel/bootstrap-layout-values.inc").items()}


LAYOUT = SimpleNamespace(**metadata())
IMAGE_POLICIES = read_table(ROOT / "kernel/uefi/image-page-policies.inc")

if __name__ == "__main__":
    print(json.dumps(metadata(), sort_keys=True, indent=2))
