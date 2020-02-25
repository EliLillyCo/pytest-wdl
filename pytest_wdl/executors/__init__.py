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
from typing import Any, Optional, Sequence, Tuple, Union, cast

from pytest_wdl.data_types import DataFile
from pytest_wdl.utils import (
    ensure_path, safe_string, find_executable_path, find_in_classpath
)

from WDL import Document, Error, Tree


ENV_JAVA_HOME = "JAVA_HOME"
ENV_JAVA_ARGS = "JAVA_ARGS"
INDENT = " " * 16


class ExecutorError(Exception):
    def __init__(self, executor: str, msg: Optional[str] = None):
        super().__init__(msg)
        self.executor = executor


class ExecutionFailedError(ExecutorError):
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
        super().__init__(executor, msg)
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
    """

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
                if key not in actual_value:
                    raise AssertionError(
                        f"Key '{key}' is in the expected value but not in "
                        f"the actual value: {expected_value} != {actual_value}"
                    )

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
    Manages the running of WDL workflows using a Java-based executor.

    Args:
        java_bin: Path to the java executable.
        java_args: Default Java arguments to use; can be overidden by passing
            `java_args=...` to `run_workflow`.
    """

    def __init__(
        self,
        java_bin: Optional[Union[str, Path]] = None,
        java_args: Optional[str] = None
    ):
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


class InputsFormatter:
    @classmethod
    def get_instance(cls) -> "InputsFormatter":
        if not hasattr(cls, "__instance"):
            setattr(cls, "__instance", object.__new__(cls))

        return getattr(cls, "__instance")

    def format_inputs(
        self, inputs_dict: dict, namespace: Optional[str] = None
    ) -> dict:
        prefix = f"{namespace}." if namespace else ""
        return dict(
            (f"{prefix}{key}", self.format_value(value))
            for key, value in inputs_dict.items()
        )

    def format_value(self, value: Any) -> Any:
        """
        Convert a primitive, DataFile, Sequence, or Dict to a JSON-serializable object.
        Currently, arbitrary objects can be serialized by implementing an `as_dict()`
        method, otherwise they are converted to strings.

        Args:
            value: The value to format.

        Returns:
            The serializable value.
        """
        if hasattr(value, "as_dict"):
            return value.as_dict()

        if isinstance(value, DataFile):
            return self._format_data_file(cast(DataFile, value))

        if isinstance(value, dict):
            return self._format_dict(cast(dict, value))

        if isinstance(value, Sequence) and not isinstance(value, str):
            return self._format_sequence(cast(Sequence, value))

        return value

    def _format_sequence(self, s: Sequence) -> list:
        return [self.format_value(val) for val in s]

    def _format_dict(self, d: dict) -> dict:
        return dict((key, self.format_value(val)) for key, val in d.items())

    def _format_data_file(self, df: DataFile) -> Union[str, dict]:
        return df.path


def parse_wdl(
    wdl_path: Path,
    import_dirs: Optional[Sequence[Path]] = (),
    check_quant: bool = False,
    **_
) -> Document:
    return Tree.load(
        str(wdl_path),
        path=[str(path) for path in import_dirs],
        check_quant=check_quant
    )


def get_target_name(
    wdl_path: Optional[Path] = None,
    wdl_doc: Optional[Document] = None,
    task_name: Optional[str] = None,
    workflow_name: Optional[str] = None,
    **kwargs
) -> Tuple[str, bool]:
    """
    Get the execution target. The order of priority is:

    - task_name
    - workflow_name
    - wdl_doc.workflow.name
    - wdl_doc.task[0].name
    - wdl_file.stem

    Args:
        wdl_path: Path to a WDL file
        wdl_doc: A miniwdl-parsed WDL document
        task_name: The task name
        workflow_name: The workflow name
        **kwargs: Additional keyword arguments to pass to `parse_wdl`

    Returns:
        A tuple (target, is_task), where `is_task` is a boolean indicating whether
        the target is a task (True) or a workflow (False).

    Raises:
        ValueError if 1) neither `task_name` nor `workflow_name` is specified and the
        WDL document contains no workflow and multiple tasks; or 2) all of the
        parameters are None.
    """
    if task_name:
        return task_name, True

    if workflow_name:
        return workflow_name, False

    if not wdl_doc and Tree:
        try:
            wdl_doc = parse_wdl(wdl_path, **kwargs)
        except Error.SyntaxError as err:
            raise RuntimeError(
                "There was an error parsing the WDL document to extract the target "
                "workflow/task name. Please specify the 'workflow_name' or 'task_name' "
                "parameter to workflow_runner()."
            ) from err

    if wdl_doc:
        if wdl_doc.workflow:
            return wdl_doc.workflow.name, False
        elif wdl_doc.tasks and len(wdl_doc.tasks) == 1:
            return wdl_doc.tasks[0].name, True
        else:
            raise ValueError(
                "WDL document has no workflow and multiple tasks, and 'task_name' "
                "is not specified"
            )

    if wdl_path:
        return safe_string(wdl_path.stem), False

    raise ValueError("At least one parameter must not be None")


def read_write_inputs(
    inputs_file: Optional[Union[str, Path]] = None,
    inputs_dict: Optional[dict] = None,
    inputs_formatter: Optional[InputsFormatter] = InputsFormatter.get_instance(),
    write_formatted_inputs: bool = True,
    **kwargs
) -> Tuple[dict, Optional[Path]]:
    """
    If `inputs_file` is specified and it exists, read its contents. Otherwise, if
    `inputs_dict` is specified, format it using `inputs_formatter` (if specified) and
    write it to `inputs_file` or a temporary file.

    Args:
        inputs_file:
        inputs_dict:
        inputs_formatter:
        write_formatted_inputs:
        kwargs:

    Returns:
        The (formatted) inputs dict and the resolved inputs file. If both `inputs_dict`
        and `inputs_file` are None, returns `({}, None)`.
    """
    if inputs_file:
        inputs_file = ensure_path(inputs_file, is_file=True, create=True)

        if inputs_file.exists():
            with open(inputs_file, "rt") as inp:
                inputs_dict_from_file = json.load(inp)
                return inputs_dict_from_file, inputs_file

    if inputs_dict:
        inputs_dict = inputs_formatter.format_inputs(inputs_dict, **kwargs)

        if write_formatted_inputs:
            if not inputs_file:
                inputs_file = Path(tempfile.mkstemp(suffix=".json")[1])

            with open(inputs_file, "wt") as out:
                json.dump(inputs_dict, out, default=str)

        return inputs_dict, inputs_file

    return {}, None
