from pathlib import Path
from typing import Optional, Union

from pytest_wdl.core import Executor
from pytest_wdl.executors import get_workflow, get_workflow_inputs

from WDL.CLI import runner


class MiniwdlExecutor(Executor):
    """
    Manages the running of WDL workflows using Cromwell.
    """

    def _run_workflow(
        self,
        wdl_script: Union[str, Path],
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
                * task_name: Name of the task to run if a workflow isn't defined.
                * inputs_file: Path to the Cromwell inputs file to use. Inputs are
                    written to this file only if it doesn't exist.

        Returns:
            Dict of outputs.

        Raises:
            Exception: if there was an error executing Cromwell
            AssertionError: if the actual outputs don't match the expected outputs
        """
        wdl_path, _ = get_workflow(self.search_paths, wdl_script)

        inputs_dict, inputs_file = get_workflow_inputs(
            inputs, kwargs.get("inputs_file")
        )

        task = kwargs.get("task_name")

        return runner(
            wdl_script,
            task=task,
            inputs_file=inputs_file,
            path=self.import_dirs
        )
