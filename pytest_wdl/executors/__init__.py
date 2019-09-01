#    Copyright 2019 Eli Lilly and Company
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.from abc import ABCMeta
import json
from pathlib import Path
import tempfile
from typing import Optional, Sequence, Tuple

from pytest_wdl.core import DataFile
from pytest_wdl.utils import ensure_path


def get_workflow_inputs(
    inputs_dict: Optional[dict] = None,
    inputs_file: Optional[Path] = None,
    namespace: Optional[str] = None
) -> Tuple[dict, Path]:
    """
    Persist workflow inputs to a file, or load workflow inputs from a file.

    Args:
        inputs_dict: Dict of input names/values.
        inputs_file: JSON file with workflow inputs.
        namespace: Name of the workflow; used to prefix the input parameters when
            creating the inputs file from the inputs dict.

    Returns:
        A tuple (inputs_dict, inputs_file)
    """
    if inputs_file:
        inputs_file = ensure_path(inputs_file)
        if inputs_file.exists():
            with open(inputs_file, "rt") as inp:
                inputs_dict = json.load(inp)
                return inputs_dict, inputs_file

    if inputs_dict:
        prefix = f"{namespace}." if namespace else ""
        inputs_dict = dict(
            (f"{prefix}{key}", make_serializable(value))
            for key, value in inputs_dict.items()
        )

        if inputs_file:
            inputs_file = ensure_path(inputs_file, is_file=True, create=True)
        else:
            inputs_file = Path(tempfile.mkstemp(suffix=".json")[1])

        with open(inputs_file, "wt") as out:
            json.dump(inputs_dict, out, default=str)

    return inputs_dict, inputs_file


def make_serializable(value):
    """
    Convert a primitive, DataFile, Sequence, or Dict to a JSON-serializable object.
    Currently, arbitrary objects can be serialized by implementing an `as_dict()`
    method, otherwise they are converted to strings.

    Args:
        value: The value to make serializable.

    Returns:
        The serializable value.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, DataFile):
        return value.path
    if isinstance(value, dict):
        return dict((k, make_serializable(v)) for k, v in value.items())
    if isinstance(value, Sequence):
        return [make_serializable(v) for v in value]
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return value


def validate_outputs(outputs: dict, expected: dict, target: str):
    for name, expected_value in expected.items():
        key = f"{target}.{name}"
        if key not in outputs:
            raise AssertionError(f"Workflow did not generate output {key}")
        if isinstance(expected_value, DataFile):
            expected_value.assert_contents_equal(outputs[key])
        else:
            assert expected_value == outputs[key]
