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
import tempfile
from typing import Optional, Sequence, Union

import subby

from pytest_wdl.executors import (
    ExecutionFailedError,
    JavaExecutor,
    get_target_name,
    read_write_inputs,
)
from pytest_wdl.executors._cromwell import (
    ENV_CROMWELL_ARGS, ENV_CROMWELL_JAR, ENV_CROMWELL_CONFIG, CromwellHelperMixin
)
from pytest_wdl.utils import LOG, ensure_path


class CromwellLocalExecutor(JavaExecutor, CromwellHelperMixin):
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
        cromwell_configuration: Optional[Union[str, Path, dict]] = None,
        cromwell_args: Optional[str] = None,
        # deprecated
        cromwell_config_file: Optional[Union[str, Path]] = None,
    ):
        super().__init__(java_bin, java_args)

        self._import_dirs = import_dirs

        self._cromwell_jar_file = self.resolve_jar_file(
            "cromwell*.jar", cromwell_jar_file, ENV_CROMWELL_JAR
        )

        if cromwell_config_file:
            LOG.warn(
                "The 'cromwell_config_file' parameter is deprecated; please use "
                "'cromwell_configuration' instead."
            )
            if not cromwell_configuration:
                cromwell_configuration = cromwell_config_file

        if not cromwell_configuration:
            config_file = os.environ.get(ENV_CROMWELL_CONFIG)

            if config_file:
                cromwell_configuration = ensure_path(config_file)

        if cromwell_configuration:
            if self.java_args:
                LOG.warn("'cromwell_configuration' is ignored when 'java_args' are set")
            else:
                if isinstance(cromwell_configuration, dict):
                    cromwell_config_file = Path(tempfile.mkstemp(suffix=".zip")[1])
                    with open(cromwell_config_file, "wt") as out:
                        json.dump(cromwell_configuration, out)
                else:
                    cromwell_config_file = ensure_path(
                        cromwell_configuration, is_file=True, exists=True
                    )

                self.java_args = f"-Dconfig.file={cromwell_config_file}"

        self._cromwell_args = cromwell_args or os.environ.get(ENV_CROMWELL_ARGS)

    def run_workflow(
        self,
        wdl_path: Path,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs,
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
            inputs_file=kwargs.get("inputs_file"), inputs_dict=inputs, namespace=target
        )
        imports_file = self._get_workflow_imports(
            self._import_dirs, kwargs.get("imports_file")
        )

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
                    "inputs": inputs_dict,
                }
                self._parse_metadata_errors(
                    metadata, target=target, error_kwargs=error_kwargs
                )
            else:
                error_kwargs["msg"] = (
                    f"Cromwell command failed but did not generate a metadata "
                    f"file at {metadata_file}"
                )

            raise ExecutionFailedError(**error_kwargs)

        if expected:
            self._validate_outputs(outputs, expected, target)

        return outputs
