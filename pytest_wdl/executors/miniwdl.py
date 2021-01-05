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
import json
import os
from pathlib import Path
from typing import Optional, Sequence

import subby
import WDL

from pytest_wdl.executors import (
    Executor, ExecutionFailedError, get_target_name, read_write_inputs
)


class MiniwdlExecutor(Executor):
    """
    Manages the running of WDL workflows using miniwdl.
    """

    def __init__(self, import_dirs: Optional[Sequence[Path]] = None):
        self._import_dirs = import_dirs or []

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
            inputs: Object that will be serialized to JSON and provided to miniwdl
                as the workflow inputs.
            expected: Dict mapping output parameter names to expected values.
            kwargs: Additional keyword arguments, mostly for debugging:
                * workflow_name: Name of the workflow to run.
                * task_name: Name of the task to run if a workflow isn't defined.
                * inputs_file: Path to the miniwdl inputs file to use. Inputs are
                    written to this file only if it doesn't exist.

        Returns:
            Dict of outputs.

        Raises:
            Exception: if there was an error executing miniwdl
            AssertionError: if the actual outputs don't match the expected outputs
        """
        check_quant = kwargs.get("check_quant", True)
        wdl_doc = WDL.load(
            str(wdl_path),
            path=[str(path) for path in self._import_dirs],
            check_quant=check_quant
        )
        namespace, is_task = get_target_name(wdl_doc=wdl_doc, **kwargs)
        inputs_dict, inputs_file = read_write_inputs(
            inputs_dict=inputs, namespace=namespace if not is_task else None,
        )
        input_arg = f"-i {inputs_file}" if inputs_file else ""
        task_arg = f"--task {namespace}" if is_task else ""
        quant_arg = "--no-quant-check" if not check_quant else ""
        path_arg = " ".join(f"-p {p}" for p in self._import_dirs)
        # TODO: we shouldn't need --copy-input-files, but without it sometimes the staged
        # input files are not available in the container.
        # Another fix is https://github.com/chanzuckerberg/miniwdl/issues/145#issuecomment-733435644
        # but we will leave --copy-input-files, so the user doesn't have to muck with Docker setings,
        # until the fissue is addressed: https://github.com/chanzuckerberg/miniwdl/issues/461
        cmd = (
            f"miniwdl run --error-json --copy-input-files {input_arg} {task_arg} "
            f"{quant_arg} {path_arg} {wdl_path}"
        )
        exe = subby.run(cmd, raise_on_error=False)

        # miniwdl writes out either outputs or error in json format to stdout
        results = json.loads(exe.output)
        if exe.ok:
            outputs = results["outputs"]

            if expected:
                self._validate_outputs(outputs, expected, namespace)

            return outputs
        else:
            error = json.loads(exe.output)
            print(error)

            pos = error.get("pos")
            if pos:
                source = f"at {pos['line']}:{pos['column']} in {pos['source']}"
            else:
                source = f"in {wdl_path}"

            failure_attrs = [error.get(x) for x in ("task", "workflow", "exit_status")]
            if any(failure_attrs):
                # RunFailed or CommandFailed
                target = failure_attrs[0] or failure_attrs[1]
                failure_dir = error.get("dir")
                failed_task = failure_attrs[0]
                failed_task_exit_status = None
                failed_task_stderr = None
                cause = error if failure_attrs[2] else error.get("cause")

                if cause:
                    if "dir" in cause:
                        failure_dir = cause["dir"]
                    failed_task_exit_status = cause["exit_status"]
                    failed_task_stderr_path = cause["stderr_file"]
                    if failed_task_stderr_path:
                        p = Path(failed_task_stderr_path)
                        if p.exists:
                            with open(p, "rt") as inp:
                                failed_task_stderr = inp.read()

                if failure_dir is not None:
                    inputs_json = Path(os.path.join(failure_dir, "inputs.json"))
                    if inputs_json.exists():
                        with open(inputs_json, "r") as inp:
                            failed_inputs = json.load(inp)

                    if failed_task is None:
                        cause_error_file = Path(os.path.join(failure_dir, "error.json"))
                        if cause_error_file.exists():
                            with open(cause_error_file, "r") as inp:
                                cause_error_json = json.load(inp)
                            if "task" in cause_error_json:
                                failed_task = cause_error_json["task"]
                else:
                    failed_inputs = None

                raise ExecutionFailedError(
                    executor="miniwdl",
                    target=target,
                    status="Failed",
                    inputs=failed_inputs,
                    executor_stderr=exe.error,
                    failed_task=failed_task,
                    failed_task_exit_status=failed_task_exit_status,
                    # failed_task_stdout=TODO,
                    failed_task_stderr=failed_task_stderr,
                    msg=error.get("message")
                )
            else:
                message = error.get("message", "unknown")
                raise RuntimeError(f"Error {source}: {message}")
