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
import logging
from pathlib import Path
import pkg_resources
from typing import Optional

from pytest_wdl.executors import Executor, get_workflow_inputs, validate_outputs

from WDL import CLI, Error, Tree, runtime


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
                * workflow_name: Name of the workflow to run.
                * task_name: Name of the task to run if a workflow isn't defined.
                * inputs_file: Path to the Cromwell inputs file to use. Inputs are
                    written to this file only if it doesn't exist.

        Returns:
            Dict of outputs.

        Raises:
            Exception: if there was an error executing Cromwell
            AssertionError: if the actual outputs don't match the expected outputs
        """

        doc = CLI.load(
            str(wdl_path),
            path=[str(path) for path in self.import_dirs],
            check_quant=kwargs.get("check_quant", True),
            read_source=CLI.read_source
        )

        task = kwargs.get("task_name")
        namespace = None
        if not task:
            if "workflow_name" in kwargs:
                namespace = kwargs["workflow_name"]
            else:
                namespace = doc.workflow.name

        inputs_dict, inputs_file = get_workflow_inputs(
            inputs,
            kwargs.get("inputs_file"),
            namespace=namespace
        )

        target, input_env, input_json = CLI.runner_input(
            doc=doc,
            inputs=[],
            input_file=inputs_file,
            empty=[],
            task=task
        )

        logger = logging.getLogger("miniwdl-run")
        logger.setLevel(CLI.NOTICE_LEVEL)
        CLI.install_coloredlogs(logger)

        try:
            logger.debug(pkg_resources.get_distribution("miniwdl"))
        except pkg_resources.DistributionNotFound as exc:
            logger.debug(
                "miniwdl version unknown ({}: {})".format(type(exc).__name__, exc)
            )
        for pkg in ["docker", "lark-parser", "argcomplete", "pygtail"]:
            logger.debug(pkg_resources.get_distribution(pkg))

        try:
            if isinstance(target, Tree.Task):
                entrypoint = runtime.run_local_task
            else:
                entrypoint = runtime.run_local_workflow
            rundir, output_env = entrypoint(target, input_env)
        except Error.EvalError as exn:
            log_source(logger, exn)
            raise
        except runtime.task.TaskFailure as exn:
            exn = exn.__cause__ or exn
            if isinstance(exn, runtime.task.CommandFailure):
                logger.error(
                    "command's standard error in %s", getattr(exn, "stderr_file")
                )
            if isinstance(getattr(exn, "pos", None), Error.SourcePosition):
                log_source(logger, exn)
            else:
                logger.error(f"{exn.__class__.__name__}, {str(exn)}")
            raise

        outputs = CLI.values_to_json(output_env, namespace=target.name)

        if expected:
            validate_outputs(outputs, expected, target.name)

        return outputs


def log_source(logger: logging.Logger, exn):
    logger.error(
        "({} Ln {} Col {}) {}{}".format(
            exn.pos.uri,
            exn.pos.line,
            exn.pos.column,
            exn.__class__.__name__,
            (", " + str(exn) if str(exn) else ""),
        )
    )
