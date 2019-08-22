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
import re
from typing import List, Optional, Union

import delegator

from pytest_wdl.executors import get_workflow, get_workflow_inputs, get_workflow_imports
from pytest_wdl.core import Executor, DataFile
from pytest_wdl.utils import LOG, ensure_path, find_executable_path, find_in_classpath


ENV_JAVA_HOME = "JAVA_HOME"
ENV_CROMWELL_JAR = "CROMWELL_JAR"
ENV_CROMWELL_CONFIG = "CROMWELL_CONFIG"
ENV_CROMWELL_ARGS = "CROMWELL_ARGS"
UNSAFE_RE = re.compile(r"[^\w.-]")


class CromwellExecutor(Executor):
    """
    Manages the running of WDL workflows using Cromwell.

    Args:
        project_root: The root path to which non-absolute WDL script paths are
            relative.
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
        project_root: Path,
        import_dirs: Optional[List[Path]] = None,
        java_bin: Optional[Union[str, Path]] = None,
        java_args: Optional[str] = None,
        cromwell_jar_file: Optional[Union[str, Path]] = None,
        cromwell_config_file: Optional[Union[str, Path]] = None,
        cromwell_args: Optional[str] = None
    ):
        self.project_root = project_root
        self.import_dirs = import_dirs

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
        wdl_script: Union[str, Path],
        workflow_name: Optional[str] = None,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        Run a WDL workflow on given inputs, and check that the output matches
        given expected values.

        Args:
            wdl_script: The WDL script to execute.
            workflow_name: The name of the workflow in the WDL script. If None, the
                name of the WDL script is used (without the .wdl extension).
            inputs: Object that will be serialized to JSON and provided to Cromwell
                as the workflow inputs.
            expected: Dict mapping output parameter names to expected values.
            kwargs: Additional keyword arguments, mostly for debugging:
                * inputs_file: Path to the Cromwell inputs file to use. Inputs are
                    written to this file only if it doesn't exist.
                * imports_file: Path to the WDL imports file to use. Imports are
                    written to this file only if it doesn't exist.
                * java_args: Additional arguments to pass to Java runtime.
                * cromwell_args: Additional arguments to pass to `cromwell run`.

        Returns:
            Dict of outputs.

        Raises:
            Exception: if there was an error executing Cromwell
            AssertionError: if the actual outputs don't match the expected outputs
        """
        wdl_path, workflow_name = get_workflow(
            self.project_root, wdl_script, workflow_name,
        )

        inputs_dict, inputs_file = get_workflow_inputs(
            workflow_name, inputs, kwargs.get("inputs_file")
        )

        imports_file = get_workflow_imports(
            self.import_dirs, kwargs.get("imports_file")
        )

        inputs_arg = f"-i {inputs_file}" if inputs_dict else ""
        imports_zip_arg = f"-p {imports_file}" if imports_file else ""
        java_args = kwargs.get("java_args", self.java_args) or ""
        cromwell_args = kwargs.get("cromwell_args", self.cromwell_args) or ""

        cmd = (
            f"{self.java_bin} {java_args} -jar {self.cromwell_jar_file} run "
            f"{cromwell_args} {inputs_arg} {imports_zip_arg} {wdl_path}"
        )
        LOG.info(
            f"Executing cromwell command '{cmd}' with inputs "
            f"{json.dumps(inputs_dict, default=str)}"
        )
        exe = delegator.run(cmd, block=True)
        if not exe.ok:
            raise Exception(
                f"Cromwell command failed; stdout={exe.out}; stderr={exe.err}"
            )

        outputs = CromwellExecutor.get_cromwell_outputs(exe.out)

        if expected:
            for name, expected_value in expected.items():
                key = f"{workflow_name}.{name}"
                if key not in outputs:
                    raise AssertionError(f"Workflow did not generate output {key}")
                if isinstance(expected_value, DataFile):
                    expected_value.assert_contents_equal(outputs[key])
                else:
                    assert expected_value == outputs[key]

        return outputs

    @staticmethod
    def get_cromwell_outputs(output):
        lines = output.splitlines(keepends=False)
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
