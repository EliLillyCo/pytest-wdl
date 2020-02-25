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
from pathlib import Path
import re
import tempfile
from typing import Optional, Sequence, Union, cast

import subby

from pytest_wdl.utils import LOG, ensure_path

ENV_CROMWELL_JAR = "CROMWELL_JAR"
ENV_CROMWELL_CONFIG = "CROMWELL_CONFIG"
ENV_CROMWELL_ARGS = "CROMWELL_ARGS"
ENV_JAVA_HOME = "JAVA_HOME"
UNSAFE_RE = re.compile(r"[^\w.-]")


class Failures:
    def __init__(
        self,
        num_failed: int,
        failed_task: str,
        failed_task_exit_status: Optional[str] = None,
        failed_task_stdout: Optional[Union[Path, str]] = None,
        failed_task_stderr: Optional[Union[Path, str]] = None,
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


class CromwellHelperMixin:
    """
    Mixin for performing common tasks for cromwell executors
    """

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
            if line == "{" and lines[i + 1].lstrip().startswith('"outputs":'):
                start = i
            elif line == "}" and start is not None:
                end = i
                break
        else:
            raise AssertionError("No outputs JSON found in Cromwell stdout")

        return json.loads("\n".join(lines[start:(end + 1)]))["outputs"]

    @classmethod
    def _parse_metadata_errors(cls, metadata, target=None, error_kwargs=None):
        failures = cls._get_failures(metadata)

        if failures:
            error_kwargs.update(
                {
                    "failed_task": failures.failed_task,
                    "failed_task_exit_status": failures.failed_task_exit_status,
                    "failed_task_stdout": failures.failed_task_stdout,
                    "failed_task_stderr": failures.failed_task_stderr,
                }
            )
            if failures.num_failed > 1:
                error_kwargs["msg"] = (
                    f"cromwell failed on {failures.num_failed} instances of "
                    f"{failures.failed_task}; only "
                    f"showing output from the first failed task"
                )
        else:
            error_kwargs["msg"] = f"cromwell failed on workflow {target}"

    @classmethod
    def _get_failures(cls, metadata: dict) -> Optional[Failures]:
        for call_name, call_metadatas in metadata["calls"].items():
            failed = list(
                filter(lambda md: md["executionStatus"] == "Failed", call_metadatas)
            )

            if failed:
                failed_call = failed[0]

                if "subWorkflowMetadata" in failed_call:
                    return cls._get_failures(failed_call["subWorkflowMetadata"])
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
    def _get_workflow_imports(
        cls,
        import_dirs: Optional[Sequence[Path]] = None,
        imports_file: Optional[Path] = None,
    ) -> Path:
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
                wdl for path in import_dirs for wdl in glob.glob(str(path / "*.wdl"))
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
                    raise_on_error=False,
                )

                if not exe.ok:
                    raise Exception(
                        f"Error creating imports zip file; stdout={exe.output}; "
                        f"stderr={exe.error}"
                    )

        return imports_path
