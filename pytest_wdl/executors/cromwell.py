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
import glob
import json
import os
from pathlib import Path
import re
import tempfile
from typing import List, Optional, Union, cast

import subby

from pytest_wdl.executors import (
    ExecutionFailedError, Executor, get_workflow_inputs, validate_outputs
)
from pytest_wdl.utils import (
    LOG, ensure_path, find_executable_path, find_in_classpath
)


ENV_JAVA_HOME = "JAVA_HOME"
ENV_CROMWELL_JAR = "CROMWELL_JAR"
ENV_CROMWELL_CONFIG = "CROMWELL_CONFIG"
ENV_CROMWELL_ARGS = "CROMWELL_ARGS"
UNSAFE_RE = re.compile(r"[^\w.-]")


class Failures:
    def __init__(
        self,
        num_failed: int,
        failed_task: str,
        failed_task_exit_status: Optional[str] = None,
        failed_task_stdout: Optional[Union[Path, str]] = None,
        failed_task_stderr: Optional[Union[Path, str]] = None
    ):
        self.num_failed = num_failed
        self.failed_task = failed_task
        self.failed_task_exit_status = failed_task_exit_status
        self._failed_task_stdout_path = None
        self._failed_task_stdout = None
        self._failed_task_stderr_path = None
        self._failed_task_stderr = None
        if isinstance(failed_task_stdout, Path):
            self._failed_task_stdout_path = cast(Path, failed_task_stdout)
        else:
            self._failed_task_stdout = cast(str, failed_task_stdout)
        if isinstance(failed_task_stderr, Path):
            self._failed_task_stderr_path = cast(Path, failed_task_stderr)
        else:
            self._failed_task_stderr = cast(str, failed_task_stderr)

    @property
    def failed_task_stdout(self):
        if self._failed_task_stdout is None and self._failed_task_stderr_path:
            self._failed_task_stdout = Failures._read_task_std(
                self._failed_task_stdout_path
            )
        return self._failed_task_stdout

    @property
    def failed_task_stderr(self):
        if self._failed_task_stderr is None and self._failed_task_stderr_path:
            self._failed_task_stderr = Failures._read_task_std(
                self._failed_task_stderr_path
            )
        return self._failed_task_stderr

    @staticmethod
    def _read_task_std(path: Path) -> Optional[str]:
        if path:
            if not path.exists():
                path = path.with_suffix(".background")
            if path.exists():
                with open(path, "rt") as inp:
                    return inp.read()


class CromwellExecutor(Executor):
    """
    Manages the running of WDL workflows using Cromwell.

    Args:
        import_dirs: Relative or absolute paths to directories containing WDL
            scripts that should be available as imports.
        java_bin: Path to the java executable.
        java_args: Default Java arguments to use; can be overidden by passing
            `java_args=...` to `run_workflow`.
        cromwell_jar_file: Path to the Cromwell JAR file.
        cromwell_args: Default Cromwell arguments to use; can be overridden by
            passing `cromwell_args=...` to `run_workflow`.
    """
    def __init__(
        self,
        import_dirs: Optional[List[Path]] = None,
        java_bin: Optional[Union[str, Path]] = None,
        java_args: Optional[str] = None,
        cromwell_jar_file: Optional[Union[str, Path]] = None,
        cromwell_config_file: Optional[Union[str, Path]] = None,
        cromwell_args: Optional[str] = None
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

        if not cromwell_jar_file:
            cromwell_jar = os.environ.get(ENV_CROMWELL_JAR)
            if cromwell_jar:
                cromwell_jar_file = ensure_path(cromwell_jar)
            else:
                cromwell_jar_file = find_in_classpath("cromwell*.jar")

        if not cromwell_jar_file:
            raise FileNotFoundError("Could not find Cromwell JAR file")

        self.cromwell_jar_file = ensure_path(
            cromwell_jar_file, is_file=True, exists=True
        )

        if not cromwell_config_file:
            config_file = os.environ.get(ENV_CROMWELL_CONFIG)
            if config_file:
                cromwell_config_file = ensure_path(config_file)
        if cromwell_config_file:
            self.cromwell_config_file = ensure_path(
                cromwell_config_file, is_file=True, exists=True
            )
        else:
            self.cromwell_config_file = None

        if not java_args and self.cromwell_config_file:
            java_args = f"-Dconfig.file={self.cromwell_config_file}"
        self.java_args = java_args

        self.cromwell_args = cromwell_args or os.environ.get(ENV_CROMWELL_ARGS)

    def run_workflow(
        self,
        wdl_path: Union[str, Path],
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
            kwargs: Additional keyword arguments, mostly for debugging:
                * workflow_name: The name of the workflow in the WDL script. If None,
                    the name of the WDL script is used (without the .wdl extension).
                * inputs_file: Path to the Cromwell inputs file to use. Inputs are
                    written to this file only if it doesn't exist.
                * imports_file: Path to the WDL imports file to use. Imports are
                    written to this file only if it doesn't exist.
                * java_args: Additional arguments to pass to Java runtime.
                * cromwell_args: Additional arguments to pass to `cromwell run`.

        Returns:
            Dict of outputs.

        Raises:
            ExecutionFailedError: if there was an error executing Cromwell
            AssertionError: if the actual outputs don't match the expected outputs
        """
        workflow_name = self._get_workflow_name(wdl_path, kwargs)

        inputs_dict, inputs_file = get_workflow_inputs(
            inputs, kwargs.get("inputs_file"), workflow_name
        )

        imports_file = self.get_workflow_imports(kwargs.get("imports_file"))

        inputs_arg = f"-i {inputs_file}" if inputs_dict else ""
        imports_zip_arg = f"-p {imports_file}" if imports_file else ""
        java_args = kwargs.get("java_args", self.java_args) or ""
        cromwell_args = kwargs.get("cromwell_args", self.cromwell_args) or ""
        metadata_file = Path.cwd() / "metadata.json"

        cmd = (
            f"{self.java_bin} {java_args} -jar {self.cromwell_jar_file} run "
            f"-m {metadata_file} {cromwell_args} {inputs_arg} {imports_zip_arg} "
            f"{wdl_path}"
        )
        LOG.info(
            f"Executing cromwell command '{cmd}' with inputs "
            f"{json.dumps(inputs_dict, default=str)}"
        )

        exe = subby.run(cmd, raise_on_error=False)

        metadata = None
        if metadata_file.exists():
            with open(metadata_file, "rt") as inp:
                metadata = json.load(inp)

        if exe.ok:
            if metadata:
                assert metadata["status"] == "Succeeded"
                outputs = metadata["outputs"]
            else:
                LOG.warning(
                    f"Cromwell command completed successfully but did not generate "
                    f"a metadata file at {metadata_file}"
                )
                outputs = CromwellExecutor.get_cromwell_outputs(exe.output)
        else:
            error_kwargs = {
                "executor": "cromwell",
                "target": workflow_name,
                "status": "Failed",
                "inputs": inputs_dict,
                "executor_stdout": exe.output,
                "executor_stderr": exe.error,
            }
            if metadata:
                failures = CromwellExecutor.get_failures(metadata)
                if failures:
                    error_kwargs.update({
                        "failed_task": failures.failed_task,
                        "failed_task_exit_status": failures.failed_task_exit_status,
                        "failed_task_stdout": failures.failed_task_stdout,
                        "failed_task_stderr": failures.failed_task_stderr
                    })
                    if failures.num_failed > 1:
                        error_kwargs["msg"] = \
                            f"cromwell failed on {failures.num_failed} instances of " \
                            f"{failures.failed_task} of {workflow_name}; only " \
                            f"showing output from the first failed task"
                else:
                    error_kwargs["msg"] = f"cromwell failed on workflow {workflow_name}"
            else:
                error_kwargs["msg"] = \
                    f"Cromwell command failed but did not generate a metadata " \
                    f"file at {metadata_file}"

            raise ExecutionFailedError(**error_kwargs)

        if expected:
            validate_outputs(outputs, expected, workflow_name)

        return outputs

    def get_workflow_imports(self, imports_file: Optional[Path] = None) -> Path:
        """
        Creates a ZIP file with all WDL files to be imported.

        Args:
            imports_file: Text file naming import directories/files - one per line.

        Returns:
            Path to the ZIP file.
        """
        write_imports = bool(self.import_dirs)
        imports_path = None

        if imports_file:
            imports_path = ensure_path(imports_file)
            if imports_path.exists():
                write_imports = False

        if write_imports and self.import_dirs:
            imports = [
                wdl
                for path in self.import_dirs
                for wdl in glob.glob(str(path / "*.wdl"))
            ]
            if imports:
                if imports_path:
                    ensure_path(imports_path, is_file=True, create=True)
                else:
                    imports_path = Path(tempfile.mkstemp(suffix=".zip")[1])

                imports_str = " ".join(imports)

                LOG.info(f"Writing imports {imports_str} to zip file {imports_path}")
                exe = subby.run(
                    f"zip -j - {imports_str}",
                    mode=bytes,
                    stdout=imports_path,
                    raise_on_error=False
                )
                if not exe.ok:
                    raise Exception(
                        f"Error creating imports zip file; stdout={exe.output}; "
                        f"stderr={exe.error}"
                    )

        return imports_path

    @staticmethod
    def get_cromwell_outputs(output) -> dict:
        lines = output.splitlines(keepends=False)
        if len(lines) < 2:
            raise Exception(f"Invalid Cromwell output: {output}")
        if lines[1].startswith("Usage"):
            # If the cromwell command is not valid, usage is printed and the
            # return code is 0 so it does not cause an exception above - we
            # have to catch it here.
            raise Exception("Invalid Cromwell command")
        start = None
        for i, line in enumerate(lines):
            if line == "{" and lines[i+1].lstrip().startswith('"outputs":'):
                start = i
            elif line == "}" and start is not None:
                end = i
                break
        else:
            raise AssertionError("No outputs JSON found in Cromwell stdout")
        return json.loads("\n".join(lines[start:(end + 1)]))["outputs"]

    @staticmethod
    def get_failures(metadata: dict) -> Optional[Failures]:
        for call_name, call_metadatas in metadata["calls"].items():
            failed = list(filter(
                lambda md: md["executionStatus"] == "Failed", call_metadatas
            ))
            if failed:
                failed_call = failed[0]
                if "subWorkflowMetadata" in failed_call:
                    return CromwellExecutor.get_failures(
                        failed_call["subWorkflowMetadata"]
                    )
                else:
                    if "returnCode" in failed_call:
                        rc = failed_call["returnCode"]
                    else:
                        rc = "Unknown"

                    stdout = stderr = None
                    if "stdout" in failed_call:
                        stdout = Path(failed_call["stdout"])
                        stderr = Path(failed_call["stderr"])
                    elif "failures" in failed_call:
                        failure = failed_call["failures"][0]
                        stderr = failure["message"]
                        if "causedBy" in failure:
                            stderr = "\n  ".join(
                                [stderr] + [cb["message"] for cb in failure["causedBy"]]
                            )

                    return Failures(len(failed), call_name, rc, stdout, stderr)
