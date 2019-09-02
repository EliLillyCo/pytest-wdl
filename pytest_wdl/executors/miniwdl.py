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

from pathlib import Path
from typing import Optional

from pytest_wdl.core import Executor
from pytest_wdl.executors import get_workflow_inputs, validate_outputs

from WDL.CLI import runner


class MiniwdlExecutor(Executor):
    """
    Manages the running of WDL workflows using Cromwell.
    """

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
                * task_name: Name of the task to run if a workflow isn't defined.
                * inputs_file: Path to the Cromwell inputs file to use. Inputs are
                    written to this file only if it doesn't exist.

        Returns:
            Dict of outputs.

        Raises:
            Exception: if there was an error executing Cromwell
            AssertionError: if the actual outputs don't match the expected outputs
        """
        task = kwargs.get("task_name")
        target = task or self._get_workflow_name(wdl_path, kwargs)

        inputs_dict, inputs_file = get_workflow_inputs(
            inputs,
            kwargs.get("inputs_file"),
            namespace=None if task else target
        )

        outputs = runner(
            str(wdl_path),
            task=task,
            input_file=inputs_file,
            path=[str(path) for path in self.import_dirs],
            verbose=False,
            debug=False
        )

        if expected:
            validate_outputs(outputs, expected, target)

        return outputs
