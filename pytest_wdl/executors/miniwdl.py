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
from typing import Optional, Sequence, cast

from pytest_wdl.executors import (
    Executor, ExecutionFailedError, get_target_name, read_write_inputs
)

from WDL import CLI, Error, Tree, runtime


class MiniwdlExecutor(Executor):
    """
    Manages the running of WDL workflows using Cromwell.
    """

    def __init__(self, import_dirs: Optional[Sequence[Path]] = None):
        self._import_dirs = import_dirs

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

        logger = logging.getLogger("miniwdl-run")
        logger.setLevel(CLI.NOTICE_LEVEL)
        CLI.install_coloredlogs(logger)

        wdl_doc = CLI.load(
            str(wdl_path),
            path=[str(path) for path in self._import_dirs],
            check_quant=kwargs.get("check_quant", True),
            read_source=CLI.read_source
        )

        namespace, is_task = get_target_name(wdl_doc=wdl_doc, **kwargs)

        inputs_dict, inputs_file = read_write_inputs(
            inputs_dict=inputs, namespace=namespace if not is_task else None,
        )

        target, input_env, input_json = CLI.runner_input(
            doc=wdl_doc,
            inputs=[],
            input_file=str(inputs_file) if inputs_file else None,
            empty=[],
            task=namespace if is_task else None
        )

        # Create config
        cfg = runtime.config.Loader(logger)
        cfg.override({
            "copy_input_files": kwargs.get("copy_input_files", False)
        })
        cfg.log_all()

        # initialize Docker
        runtime.task.LocalSwarmContainer.global_init(cfg, logger)

        try:
            rundir, output_env = runtime.run(cfg, target, input_env, run_dir=None)
        except Error.EvalError as err:  # TODO: test errors
            MiniwdlExecutor.log_source(logger, err)
            raise
        except Error.RuntimeError as err:
            MiniwdlExecutor.log_source(logger, err)

            if isinstance(err, runtime.error.RunFailed):
                # This will be a workflow- or a task-level failure, depending on
                # whether a workflow or task was executed. If it is workflow-level,
                # we need to get the task-level error that caused the workflow to fail.
                if isinstance(err.exe, Tree.Workflow):
                    err = err.__cause__

                task_err = cast(runtime.error.RunFailed, err)
                cause = task_err.__cause__
                failed_task_exit_status = None
                failed_task_stderr = None
                if isinstance(cause, runtime.error.CommandFailed):
                    # If the task failed due to an error in the command, populate the
                    # command exit status and stderr.
                    cmd_err = cast(runtime.error.CommandFailed, cause)
                    failed_task_exit_status = cmd_err.exit_status
                    failed_task_stderr = MiniwdlExecutor.read_miniwdl_command_std(
                        cmd_err.stderr_file
                    )

                raise ExecutionFailedError(
                    "miniwdl",
                    namespace,
                    status="Failed",
                    inputs=task_err.exe.inputs,
                    failed_task=task_err.exe.name,
                    failed_task_exit_status=failed_task_exit_status,
                    failed_task_stderr=failed_task_stderr
                ) from err
            else:
                raise

        outputs = CLI.values_to_json(output_env, namespace=target.name)

        if expected:
            self._validate_outputs(outputs, expected, target.name)

        return outputs

    @staticmethod
    def read_miniwdl_command_std(path: Optional[str] = None) -> Optional[str]:
        if path:
            p = Path(path)

            if p.exists():
                with open(path, "rt") as inp:
                    return inp.read()

    @staticmethod
    def log_source(logger: logging.Logger, exn: Exception):
        if isinstance(exn, runtime.error.RunFailed):
            pos = cast(runtime.error.RunFailed, exn).exe.pos
        elif hasattr(exn, "pos"):
            pos = cast(Error.SourcePosition, getattr(exn, "pos"))
        else:
            return
        if pos:
            logger.error(
                "({} Ln {} Col {}) {}{}".format(
                    pos.uri,
                    pos.line,
                    pos.column,
                    exn.__class__.__name__,
                    (", " + str(exn) if str(exn) else ""),
                )
            )
