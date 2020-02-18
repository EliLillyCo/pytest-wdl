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
import time
from typing import Optional, Sequence, Union, cast

import requests
import subby
from requests.auth import HTTPBasicAuth
from pytest_wdl.executors import (
    ExecutionFailedError,
    JavaExecutor,
    Executor,
    get_target_name,
    read_write_inputs,
)
from pytest_wdl.utils import LOG, ensure_path


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





class CromwellHelperMixin():
    """
    Mixin for performing common tasks for cromwell executors
    """

    @classmethod
    def _get_failures(cls, metadata: dict) -> Optional[Failures]:
        for call_name, call_metadatas in metadata["calls"].items():
            failed = list(filter(
                lambda md: md["executionStatus"] == "Failed", call_metadatas
            ))
            if failed:
                failed_call = failed[0]
                if "subWorkflowMetadata" in failed_call:
                    return cls._get_failures(
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

    @classmethod
    def _get_cromwell_outputs(cls, output) -> dict:
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


    @classmethod
    def _parse_metadata_errors(cls,metadata,target = None,error_kwargs = None):
        failures = cls._get_failures(metadata)
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
                    f"{failures.failed_task}; only " \
                    f"showing output from the first failed task"
        else:
            error_kwargs["msg"] = f"cromwell failed on workflow {target}"

    @classmethod
    def _get_workflow_imports(cls,import_dirs: Optional[Union[Path,str]], imports_file: Optional[Path] = None) -> Path:
        """
        Creates a ZIP file with all WDL files to be imported.

        Args:
            imports_file: Text file naming import directories/files - one per line.

        Returns:
            Path to the ZIP file.
        """
        write_imports = bool(import_dirs)
        imports_path = None

        if imports_file:
            imports_path = ensure_path(imports_file)
            if imports_path.exists():
                write_imports = False

        if write_imports and import_dirs:
            imports = [
                wdl
                for path in import_dirs
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


class CromwellServerExecutor(Executor,CromwellHelperMixin):
    """
    Manages the running of WDL workflows using a remote Cromwell running in Server mode.

    Args:
        import_dirs: Relative or absolute paths to directories containing WDL
            scripts that should be available as imports.
        cromwell_api_url: The full URL where this cromwell exists
            `http://localhost:8000/api/workflows/v1`
        cromwell_api_username: The username to pass to the cromwell API if protected by basic auth
        cromwell_api_password: The password to pass to the cromwell API if protected by basic auth
        cromwell_runtime_options: An options file that will be passed to cromwell
    """

    def __init__(
        self,
        import_dirs: Optional[Sequence[Path]] = None,
        cromwell_api_url: Optional[str] = None,
        cromwell_api_username: Optional[str] = None,
        cromwell_api_password: Optional[str] = None,
        cromwell_runtime_options: Optional[Union[dict, Path]] = None
    ):
        super().__init__()
        self._import_dirs = import_dirs

        if not cromwell_api_url:
            cromwell_api_url = "http://localhost:8000/api/workflows/v1"

        if cromwell_api_username and cromwell_api_password:
            self._auth = HTTPBasicAuth(cromwell_api_username, cromwell_api_password)
            print(self._auth)
        else:
            self._auth = None

        self._cromwell_api_url = cromwell_api_url
        self._cromwell_runtime_options = cromwell_runtime_options

    def _resp_to_json(self,resp,target=None,inputs_dict=None):
        if resp.ok:
            return resp.json()
        else:
            error_kwargs = {
                "executor": "cromwell-server",
                "target": target,
                "status": "Failed",
                "inputs": inputs_dict
            }
            if resp.reason:
                error_kwargs["msg"] = resp.reason
            raise ExecutionFailedError(**error_kwargs)

    def _poll_until_terminal(self,id = None, target= None, inputs_dict=None, timeout=3600):
        terminal_states = ["Succeeded","Aborted","Failed"]
        status_url = f"{self._cromwell_api_url}/{id}/status"
        is_terminal = False
        start = time.time()
        time.sleep(5)
        while not is_terminal and (time.time() - start) < timeout:
            with requests.get(status_url, auth = self._auth) as resp:
                status_object = self._resp_to_json(resp,target,inputs_dict)
                if status_object["status"] in terminal_states:
                    return
                else:
                    time.sleep(5)
        LOG.error(
            f"Encountered timeout for run with id {id}"
        )
        error_kwargs = {
            "executor": "cromwell-server",
            "target": target,
            "status": "Failed",
            "inputs": inputs_dict,
            "msg": f"Encountered timeout for run with id {id}"
        }
        raise ExecutionFailedError(**error_kwargs)


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
        target, is_task = get_target_name(
            wdl_path=wdl_path, import_dirs=self._import_dirs, **kwargs
        )
        inputs_dict, inputs_file = read_write_inputs(
            inputs_dict=inputs, namespace=target
        )


        imports_file = self._get_workflow_imports(self._import_dirs,kwargs.get("imports_file"))

        files = {
            "workflowSource": open(wdl_path,"r")
        }

        if inputs_dict:
            if isinstance(inputs_dict,dict):
                files["workflowInputs"] = json.dumps(inputs_dict)
            else:
                files["workflowInputs"] = open(inputs_dict,"r",encoding="utf-8")

        if imports_file:
            files["workflowDependencies"] = open(imports_file,"rb")

        if self._cromwell_runtime_options:
            if isinstance(inputs_dict, dict):
                files["workflowOptions"] = json.dumps(self._cromwell_runtime_options)
            else:
                files["workflowOptions"] = open(self._cromwell_runtime_options,"r")



        LOG.info(
            f"Executing cromwell server '{self._cromwell_api_url}' with inputs "
            f"{json.dumps(inputs_dict, default=str)}"
        )

        with requests.post(self._cromwell_api_url, files=files, auth=self._auth) as resp:
            status_object = self._resp_to_json(resp,target,inputs_dict)
            run_id = status_object["id"]
            LOG.info(
                f"Executing on cromwell with id {run_id}. Waiting until terminal state is reached"
            )
        self._poll_until_terminal(run_id, target, inputs_dict)
        metadata_url = f"{self._cromwell_api_url}/{run_id}/metadata"
        outputs = None
        with requests.get(metadata_url,auth = self._auth) as metadata_response:
            metadata = self._resp_to_json(metadata_response, target, inputs_dict)
            if metadata["status"] == "Succeeded":
                outputs = metadata["outputs"]
            else:
                error_kwargs = {
                    "executor": "cromwell",
                    "target": target,
                    "status": "Failed",
                    "inputs": inputs_dict
                }
                self._parse_metadata_errors(metadata,target=target, error_kwargs=error_kwargs)
                raise ExecutionFailedError(**error_kwargs)

        if expected:
            self._validate_outputs(outputs, expected, target)
        return outputs




class CromwellExecutor(JavaExecutor,CromwellHelperMixin):
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
        import_dirs: Optional[Sequence[Path]] = None,
        java_bin: Optional[Union[str, Path]] = None,
        java_args: Optional[str] = None,
        cromwell_jar_file: Optional[Union[str, Path]] = None,
        cromwell_config_file: Optional[Union[str, Path]] = None,
        cromwell_args: Optional[str] = None
    ):
        super().__init__(java_bin, java_args)

        self._import_dirs = import_dirs

        self._cromwell_jar_file = self.resolve_jar_file(
            "cromwell*.jar", cromwell_jar_file, ENV_CROMWELL_JAR
        )

        if not cromwell_config_file:
            config_file = os.environ.get(ENV_CROMWELL_CONFIG)
            if config_file:
                cromwell_config_file = ensure_path(config_file)

        if cromwell_config_file:
            self._cromwell_config_file = ensure_path(
                cromwell_config_file, is_file=True, exists=True
            )
        else:
            self._cromwell_config_file = None

        if not self.java_args and self._cromwell_config_file:
            self.java_args = f"-Dconfig.file={self._cromwell_config_file}"

        self._cromwell_args = cromwell_args or os.environ.get(ENV_CROMWELL_ARGS)

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
        target, is_task = get_target_name(
            wdl_path=wdl_path, import_dirs=self._import_dirs, **kwargs
        )
        if is_task:
            raise ValueError(
                "Cromwell cannot execute tasks independently of a workflow"
            )

        inputs_dict, inputs_file = read_write_inputs(
            inputs_dict=inputs, namespace=target
        )

        imports_file = self._get_workflow_imports(self._import_dirs,kwargs.get("imports_file"))
        inputs_arg = f"-i {inputs_file}" if inputs_file else ""
        imports_zip_arg = f"-p {imports_file}" if imports_file else ""
        java_args = kwargs.get("java_args", self.java_args) or ""
        cromwell_args = kwargs.get("cromwell_args", self._cromwell_args) or ""
        metadata_file = Path.cwd() / "metadata.json"

        cmd = (
            f"{self.java_bin} {java_args} -jar {self._cromwell_jar_file} run "
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
                outputs = self._get_cromwell_outputs(exe.output)
        else:
            error_kwargs = {
                "executor": "cromwell",
                "target": target,
                "status": "Failed",
                "inputs": inputs_dict,
                "executor_stdout": exe.output,
                "executor_stderr": exe.error,
            }
            if metadata:
                error_kwargs = {
                    "executor": "cromwell",
                    "target": target,
                    "status": "Failed",
                    "inputs": inputs_dict
                }
                self._parse_metadata_errors(metadata,target=target, error_kwargs=error_kwargs)
            else:
                error_kwargs["msg"] = \
                    f"Cromwell command failed but did not generate a metadata " \
                    f"file at {metadata_file}"

            raise ExecutionFailedError(**error_kwargs)

        if expected:
            self._validate_outputs(outputs, expected, target)

        return outputs





