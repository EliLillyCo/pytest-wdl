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
import os
from pathlib import Path
import tempfile
import textwrap
from typing import Any, Callable, List, Optional, Sequence, Tuple, Union, cast

from pytest_wdl.data_types import DataFile
from pytest_wdl.utils import (
    ensure_path, safe_string, find_executable_path, find_in_classpath
)

from WDL import Tree


ENV_JAVA_HOME = "JAVA_HOME"
ENV_JAVA_ARGS = "JAVA_ARGS"
INDENT = " " * 16


class ExecutionFailedError(Exception):
    def __init__(
        self,
        executor: str,
        target: str,
        status: str,
        inputs: Optional[dict] = None,
        executor_stdout: Optional[str] = None,
        executor_stderr: Optional[str] = None,
        failed_task: Optional[str] = None,
        failed_task_exit_status: Optional[int] = None,
        failed_task_stdout: Optional[str] = None,
        failed_task_stderr: Optional[str] = None,
        msg: Optional[str] = None
    ):
        if msg is None:
            if failed_task and failed_task != target:
                msg = f"{executor} failed with status {status} while running task " \
                      f"{failed_task} of {target}"
            else:
                msg = f"{executor} failed with status {status} while running {target}"
        super().__init__(msg)
        self.executor = executor
        self.target = target
        self.status = status
        self.inputs = inputs
        self.executor_stdout = executor_stdout
        self.executor_stderr = executor_stderr
        self.failed_task = failed_task
        self.failed_task_exit_status = failed_task_exit_status
        self.failed_task_stdout = failed_task_stdout
        self.failed_task_stderr = failed_task_stderr

    @property
    def exit_status_str(self) -> str:
        if self.failed_task_exit_status:
            return str(self.failed_task_exit_status)
        else:
            return "Unknown"

    def __str__(self):
        def wrap_std(std: str):
            if std:
                return "\n" + textwrap.indent(std, INDENT)
            else:
                return " None"

        return textwrap.dedent(f"""
        {self.args[0]}:
            inputs:
                {self.inputs}
            executor_stdout:{wrap_std(self.executor_stdout)}
            executor_stderr:{wrap_std(self.executor_stderr)}
            failed_task_exit_status: {self.exit_status_str}
            failed_task_stdout:{wrap_std(self.failed_task_stdout)}
            failed_task_stderr:{wrap_std(self.failed_task_stderr)}
        """)


class Executor(metaclass=ABCMeta):
    """
    Base class for WDL workflow executors.

    Args:
        import_dirs: Relative or absolute paths to directories containing WDL
            scripts that should be available as imports.
    """
    def __init__(self, import_dirs: Optional[List[Path]] = None):
        self.import_dirs = import_dirs or []

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
            ExecutionFailedError: if there was an error executing the workflow
            AssertionError: if the actual outputs don't match the expected outputs
        """

    def _get_workflow_name(self, wdl_path: Path, kwargs):
        if "workflow_name" in kwargs:
            return kwargs["workflow_name"]
        elif Tree:
            doc = Tree.load(
                str(wdl_path),
                path=[str(path) for path in self.import_dirs],
                check_quant=kwargs.get("check_quant", False)
            )
            return doc.workflow.name
        else:  # TODO: test this
            return safe_string(wdl_path.stem)

    @classmethod
    def _get_workflow_inputs(
        cls: "Executor",
        inputs_dict: Optional[dict] = None,
        namespace: Optional[str] = None,
        kwargs: Optional[dict] = None,
        write_inputs: bool = True,
    ) -> Union[dict, Tuple[dict, Path]]:
        """
        Persist workflow inputs to a file, or load workflow inputs from a file.

        Args:
            inputs_dict: Dict of input names/values.
            namespace: Name of the workflow; used to prefix the input parameters when
                creating the inputs file from the inputs dict.
            write_inputs: Whether to write inputs to `inputs_file`, or a temporary file
                if `inputs_file` is None.
            kwargs:

        Returns:
            A tuple (inputs_dict, inputs_file) if `write_inputs` is True, otherwise
            just inputs_dict.
        """
        inputs_file = kwargs.get("inputs_file", None) if kwargs else None

        if inputs_file:
            inputs_dict_from_file, inputs_file = cls._read_inputs(inputs_file)
            if inputs_dict_from_file:
                return inputs_dict_from_file, inputs_file

        if inputs_dict:
            inputs_dict = cls._format_inputs(inputs_dict, namespace, kwargs)

        if not write_inputs:
            return inputs_dict
        elif not inputs_file:
            raise ValueError("Missing keyword argument 'inputs_file'")
        else:
            inputs_file = cls._write_inputs(inputs_dict, inputs_file)
            return inputs_dict, inputs_file

    @classmethod
    def _read_inputs(cls, inputs_file: Path) -> Tuple[Optional[dict], Path]:
        inputs_file = ensure_path(inputs_file)
        inputs_dict = None
        if inputs_file.exists():
            with open(inputs_file, "rt") as inp:
                inputs_dict = json.load(inp)
        return inputs_dict, inputs_file

    @classmethod
    def _format_inputs(
        cls, inputs_dict: dict, namespace: Optional[str], kwargs: dict
    ) -> dict:
        prefix = f"{namespace}." if namespace else ""
        return dict(
            (f"{prefix}{key}", cls._make_serializable(value))
            for key, value in inputs_dict.items()
        )

    @classmethod
    def _write_inputs(cls, inputs_dict: dict, inputs_file: Path) -> Path:
        if inputs_file:
            inputs_file = ensure_path(inputs_file, is_file=True, create=True)
        else:
            inputs_file = Path(tempfile.mkstemp(suffix=".json")[1])

        with open(inputs_file, "wt") as out:
            json.dump(inputs_dict, out, default=str)

        return inputs_file

    @classmethod
    def _make_serializable(
        cls: "Executor", value,
        data_file_serializer: Callable[[DataFile], Any] = lambda df: df.path
    ):
        """
        Convert a primitive, DataFile, Sequence, or Dict to a JSON-serializable object.
        Currently, arbitrary objects can be serialized by implementing an `as_dict()`
        method, otherwise they are converted to strings.

        Args:
            value: The value to make serializable.
            data_file_serializer: Function used to make a DataFile serializable.

        Returns:
            The serializable value.
        """
        if isinstance(value, str):
            return value
        if isinstance(value, DataFile):
            return data_file_serializer(cast(DataFile, value))
        if isinstance(value, dict):
            return dict((k, cls._make_serializable(v)) for k, v in value.items())
        if isinstance(value, Sequence):
            return [cls._make_serializable(v) for v in value]
        if hasattr(value, "as_dict"):
            return value.as_dict()
        return value

    @classmethod
    def _validate_outputs(
        cls: "Executor", outputs: dict, expected: dict, target: str
    ) -> None:
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
            cls._compare_output_values(expected_value, outputs[key], key)

    @classmethod
    def _compare_output_values(
        cls: "Executor", expected_value, actual_value, name: str
    ) -> None:
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
                cls._compare_output_values(exp, act, f"{name}[{i}]")
        elif isinstance(expected_value, dict):
            if len(expected_value) != len(actual_value):
                raise AssertionError(
                    f"Expected and actual values differ in length for {name}: "
                    f"{len(expected_value)} != {len(actual_value)}"
                )
            for key, exp in expected_value.items():
                assert key in actual_value
                cls._compare_output_values(exp, actual_value[key], f"{name}.{key}")
        elif isinstance(expected_value, DataFile):
            # TODO: pass name
            expected_value.assert_contents_equal(actual_value)
        elif expected_value != actual_value:
            raise AssertionError(
                f"Expected and actual values differ for {name}: "
                f"{expected_value} != {actual_value}"
            )


class JavaExecutor(Executor, metaclass=ABCMeta):
    """
    Manages the running of WDL workflows using Cromwell.

    Args:
        import_dirs:
        java_bin: Path to the java executable.
        java_args: Default Java arguments to use; can be overidden by passing
            `java_args=...` to `run_workflow`.
    """

    def __init__(
        self,
        import_dirs: Optional[List[Path]] = None,
        java_bin: Optional[Union[str, Path]] = None,
        java_args: Optional[str] = None
    ):
        super().__init__(import_dirs)

        if not java_bin:
            java_home = os.environ.get(ENV_JAVA_HOME)
            if java_home:
                java_bin = Path(java_home) / "bin" / "java"
            else:
                java_bin = find_executable_path("java")

        if not java_bin:
            raise FileNotFoundError("Could not find java executable")

        self.java_bin = ensure_path(
            java_bin, exists=True, is_file=True, executable=True
        )

        self.java_args = java_args or os.environ.get(ENV_JAVA_ARGS)

    @staticmethod
    def resolve_jar_file(
        file_name_pattern: str, jar_path: Optional[Path] = None,
        env_var: Optional[str] = None,
    ):
        if not jar_path:
            path_str = None
            if env_var:
                path_str = os.environ.get(env_var)
            if path_str:
                jar_path = ensure_path(path_str)
            else:
                jar_path = find_in_classpath(file_name_pattern)

        if not jar_path:
            raise FileNotFoundError(f"Could not find JAR file {file_name_pattern}")

        return ensure_path(jar_path, is_file=True, exists=True)
