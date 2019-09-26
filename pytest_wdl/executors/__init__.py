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
#    limitations under the License.
from abc import ABCMeta, abstractmethod
import json
from pathlib import Path
import tempfile
from typing import List, Optional, Sequence, Tuple

from xphyle import open_

from pytest_wdl.data_types import DataFile
from pytest_wdl.utils import ensure_path, safe_string

from WDL import Tree


class Executor(metaclass=ABCMeta):
    """
    Base class for WDL workflow executors.

    Args:
        import_dirs: Relative or absolute paths to directories containing WDL
            scripts that should be available as imports.
    """
    def __init__(self, import_dirs: Optional[List[Path]] = None):
        self.import_dirs = import_dirs or []

    def _get_workflow_name(self, wdl_path: Path, kwargs: dict):
        if "workflow_name" in kwargs:
            return kwargs["workflow_name"]
        elif Tree:
            if "check_quant" not in kwargs:
                kwargs["check_quant"] = False
            doc = Tree.load(
                str(wdl_path),
                path=[str(path) for path in self.import_dirs],
                **kwargs
            )
            return doc.workflow.name
        else:
            return safe_string(wdl_path.stem)

    @abstractmethod
    def run_workflow(
        self,
        wdl_path: Path,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        Run a WDL workflow on given inputs, and check that the output matches
        given expected values.

        Args:
            wdl_path: The WDL script to execute.
            inputs: Object that will be serialized to JSON and provided to Cromwell
                as the workflow inputs.
            expected: Dict mapping output parameter names to expected values.
            kwargs: Additional executor-specific keyword arguments (mostly for
                debugging)

        Returns:
            Dict of outputs.

        Raises:
            Exception: if there was an error executing the workflow
            AssertionError: if the actual outputs don't match the expected outputs
        """


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
            with open_(inputs_file, "rt") as inp:
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

        with open_(inputs_file, "wt") as out:
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


def validate_outputs(outputs: dict, expected: dict, target: str) -> None:
    """
    Validate expected and actual outputs are equal.

    Args:
        outputs: Actual outputs
        expected: Expected outputs
        target: Execution target (i.e. workflow name)

    Raises:
        AssertionError
    """
    for name, expected_value in expected.items():
        key = f"{target}.{name}"
        if key not in outputs:
            raise AssertionError(f"Workflow did not generate output {key}")
        compare_output_values(expected_value, outputs[key], key)


def compare_output_values(expected_value, actual_value, name: str) -> None:
    """
    Compare two values and raise an error if they are not equal.

    Args:
        expected_value:
        actual_value:
        name: Name of the output being compared

    Raises:
        AssertionError
    """
    if actual_value is None:
        if expected_value is None:
            return
        else:
            raise AssertionError(
                f"Expected and actual values differ for {name}: "
                f"{expected_value} != {actual_value}"
            )
    elif isinstance(expected_value, list):
        if len(expected_value) != len(actual_value):
            raise AssertionError(
                f"Expected and actual values differ in length for {name}: "
                f"{len(expected_value)} != {len(actual_value)}"
            )
        for i, (exp, act) in enumerate(zip(expected_value, actual_value)):
            compare_output_values(exp, act, f"{name}[{i}]")
    elif isinstance(expected_value, dict):
        if len(expected_value) != len(actual_value):
            raise AssertionError(
                f"Expected and actual values differ in length for {name}: "
                f"{len(expected_value)} != {len(actual_value)}"
            )
        for key, exp in expected_value.items():
            assert key in actual_value
            compare_output_values(exp, actual_value[key], f"{name}.{key}")
    elif isinstance(expected_value, DataFile):
        # TODO: pass name
        expected_value.assert_contents_equal(actual_value)
    elif expected_value != actual_value:
        raise AssertionError(
            f"Expected and actual values differ for {name}: "
            f"{expected_value} != {actual_value}"
        )
