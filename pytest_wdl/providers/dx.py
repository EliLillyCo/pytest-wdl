# Copyright 2019 Eli Lilly and Company
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from argparse import Namespace
import contextlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union, cast
from unittest.mock import patch

from pytest_wdl import config
from pytest_wdl.data_types import DataFile
from pytest_wdl.executors import (
    ExecutorError,
    ExecutionFailedError,
    InputsFormatter,
    JavaExecutor,
    get_workflow_name,
)
from pytest_wdl.localizers import UrlLocalizer
from pytest_wdl.url_schemes import Method, Request, Response, UrlHandler
from pytest_wdl.utils import LOG, ensure_path, verify_digests

try:
    # test whether dxpy is installed and the user is logged in
    import dxpy
    assert dxpy.SECURITY_CONTEXT
    assert dxpy.whoami()
except:
    LOG.exception(
        "DNAnexus (dx) extensions require that a) you install 'dxpy' "
        "(try 'pip install dxpy') and b) you log into your DNAnexus account via the "
        "command line (try 'dx login')."
    )
    raise

from dxpy.scripts import dx
from dxpy.utils.job_log_client import DXJobLogStreamClient
import subby


ENV_JAVA_HOME = "JAVA_HOME"
ENV_DXWDL_JAR = "DXWDL_JAR"
ENV_DX_USERNAME = "DX_USERNAME"
OUTPUT_STAGE = "stage-outputs"
DX_LINK_KEY = "$dnanexus_link"
DX_STRUCT_KEY = "___"
DX_FILES_SUFFIX = "___dxfiles"
STDOUT_LOG = "STDOUT"
STDERR_LOG = "STDERR"


@contextlib.contextmanager
def login(logout: bool = False):
    if dxpy.SECURITY_CONTEXT:
        try:
            dxpy.whoami()
        except dxpy.exceptions.InvalidAuthentication:
            dxpy.SECURITY_CONTEXT = None

    if dxpy.SECURITY_CONTEXT:
        yield
    else:
        conf = config.get_instance().get_provider_defaults("dxwdl")
        username = conf.get("username")
        token = conf.get("token")

        if ENV_DX_USERNAME not in os.environ and username:
            os.environ[ENV_DX_USERNAME] = username

        args = Namespace(
            auth_token=None,
            token=token,
            host=None,
            port=None,
            protocol="https",
            timeout=conf.get("timeout", "1d"),
            save=True,
            staging=False,
            projects=False
        )

        try:
            if not token and "password" in conf:
                with patch("builtins.input", return_value=username), \
                        patch("getpass.getpass", return_value=conf["password"]):
                    dx.login(args)
            else:
                # If token is not specified, this will require interactive login
                dx.login(args)
            yield
        finally:
            if logout:
                dx.logout(args)


class DxResponse(Response):
    def __init__(self, file_id: str, project_id: Optional[str] = None):
        self.file_id = file_id
        self.project_id = project_id

    def download_file(
        self,
        destination: Path,
        show_progress: bool = False,
        digests: Optional[dict] = None
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)

        with login():
            dxpy.download_dxfile(
                self.file_id,
                str(destination),
                show_progress=show_progress,
                project=self.project_id
            )

        if digests:
            verify_digests(destination, digests)


class DxUrlHandler(UrlHandler):
    @property
    def scheme(self) -> str:
        return "dx"

    @property
    def handles(self) -> Sequence[Method]:
        return [Method.OPEN]

    def urlopen(self, request: Request) -> Response:
        url = request.get_full_url()

        if not url.startswith("dx://"):  # TODO: test this
            raise ValueError(f"Expected URL to start with 'dx://'; got {url}")

        obj_id = url[5:]

        if ":" in obj_id:
            project_id, file_id = obj_id.split(":")
        else:
            project_id = None
            file_id = obj_id

        return DxResponse(file_id, project_id)


class DxWdlExecutor(JavaExecutor):
    # TODO: not thread safe - tests cannot be parallelized
    _workflow_cache: Dict[Path, dxpy.DXWorkflow] = {}
    _data_cache = {}

    def __init__(
        self,
        import_dirs: Optional[List[Path]] = None,
        java_bin: Optional[Union[str, Path]] = None,
        java_args: Optional[str] = None,
        dxwdl_jar_file: Optional[Union[str, Path]] = None,
        dxwdl_cache_dir: Optional[Union[str, Path]] = None,
    ):
        super().__init__(java_bin, java_args)
        self._import_dirs = import_dirs
        self._inputs_formatter = DxInputsFormatter()
        self._dxwdl_jar_file = self.resolve_jar_file(
            "dxWDL*.jar", dxwdl_jar_file, ENV_DXWDL_JAR
        )
        if dxwdl_cache_dir:
            self._dxwdl_cache_dir = ensure_path(dxwdl_cache_dir)
            self._cleanup_cache = False
        else:
            self._dxwdl_cache_dir = ensure_path(tempfile.mkdtemp())
            self._cleanup_cache = True

    def run_workflow(
        self,
        wdl_path: Path,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs
    ) -> dict:
        # TODO: handle "task_name" kwarg - run app instead of workflow
        namespace = kwargs.get("stage_id", "stage-common")
        inputs_dict = None

        if "inputs_file" in kwargs:
            inputs_file = ensure_path(kwargs["inputs_file"])

            if inputs_file.exists():
                with open(inputs_file, "rt") as inp:
                    inputs_dict = json.load(inp)

        if not inputs_dict:
            inputs_dict = self._inputs_formatter.format_inputs(
                inputs, namespace, **kwargs
            )

        try:
            with login():
                workflow_name = get_workflow_name(
                    wdl_path, import_dirs=self._import_dirs, **kwargs
                )
                workflow = self._resolve_workflow(wdl_path, workflow_name, kwargs)
                analysis = workflow.run(inputs_dict)

                try:
                    analysis.wait_on_done()

                    outputs = self._get_analysis_outputs(analysis, expected.keys())

                    if expected:
                        self._validate_outputs(outputs, expected, OUTPUT_STAGE)

                    return outputs
                except dxpy.exceptions.DXJobFailureError:
                    raise ExecutionFailedError(
                        "dxWDL",
                        workflow_name,
                        analysis.describe()["state"],
                        inputs_dict,
                        **self._get_failed_task(analysis)
                    )
                finally:
                    if self._cleanup_cache:
                        shutil.rmtree(self._dxwdl_cache_dir)
        except dxpy.exceptions.InvalidAuthentication as ierr:
            raise ExecutorError("dxwdl", "Invalid DNAnexus credentials/token") from ierr
        except dxpy.exceptions.ResourceNotFound as rerr:
            raise ExecutorError("dxwdl", "Required resource was not found") from rerr
        except dxpy.exceptions.PermissionDenied as perr:
            raise ExecutorError(
                "dxwdl", f"You must have at least CONTRIBUTE permission"
            ) from perr

    def _resolve_workflow(
        self,
        wdl_path: Path,
        workflow_name: str,
        kwargs: dict,
    ) -> dxpy.DXWorkflow:
        if wdl_path in DxWdlExecutor._workflow_cache:
            return DxWdlExecutor._workflow_cache[wdl_path]

        project_id = (
            kwargs.get("workflow_project_id") or
            kwargs.get("project_id", dxpy.PROJECT_CONTEXT_ID)
        )
        folder = kwargs.get("workflow_folder") or kwargs.get("folder", "/")

        # # This probably isn't necessary, since (I think) dxWDL creates the folder
        # # if it doesn't exist
        # if not folder:
        #     folder = "/"
        # else:
        #     # Check that the project exists and create the folder (any any missing
        #     # parents) if it doesn't exist. May also fail if the user does not have
        #     # write access to the project.
        #     project = dxpy.DXProject(project_id)
        #     project.new_folder(folder, parents=True)

        build_workflow = kwargs.get("force", False)
        workflow_id = None

        if not build_workflow:
            existing_workflow = list(dxpy.find_data_objects(
                classname="workflow",
                name=workflow_name,
                project=project_id,
                folder=folder,
                describe={
                    "created": True
                }
            ))

            if not existing_workflow:
                build_workflow = True
            else:
                created = existing_workflow[0]["describe"]["created"]
                if wdl_path.stat().st_mtime > created:
                    build_workflow = True
                elif self._import_dirs:
                    for import_dir in self._import_dirs:
                        for imp in import_dir.glob("*.wdl"):
                            if imp.stat().st_mtime > created:
                                build_workflow = True
                                break
                    else:
                        workflow_id = existing_workflow[0]["id"]

        if build_workflow:
            java_args = kwargs.get("java_args", self.java_args) or ""
            imports_args = " ".join(f"-imports {d}" for d in self._import_dirs)
            extras = kwargs.get("extras")
            extras_arg = f"-extras {extras}" if extras else ""
            archive = kwargs.get("archive")
            archive_arg = "-a" if archive else "-f"

            cmd = (
                f"{self.java_bin} {java_args} -jar {self._dxwdl_jar_file} compile "
                f"{wdl_path} -destination {project_id}:{folder} {imports_args} "
                f"{extras_arg} {archive_arg}"
            )

            LOG.info(f"Building workflow with command '{cmd}'")
            workflow_id = subby.sub(cmd).splitlines(False)[-1]

        workflow = dxpy.DXWorkflow(workflow_id)
        DxWdlExecutor._workflow_cache[wdl_path] = workflow
        return workflow

    @classmethod
    def _get_failed_task(cls, analysis: dxpy.DXAnalysis) -> dict:
        """
        Find the causal failure within an execution tree and get the logs.
        """
        query = {
            "project": dxpy.WORKSPACE_ID,
            "state": "failed",
            "describe": {
                "stateTransitions": True
            },
            "include_subjobs": True,
            "root_execution": analysis.get_id()
        }
        cause = None
        cause_ts = None
        for execution_result in dxpy.find_executions(**query):
            if "stateTransitions" in execution_result["describe"]:
                for st in execution_result["describe"]["stateTransitions"]:
                    if st["newState"] == "failed":
                        ts = st["setAt"]
                        if cause is None or ts < cause_ts:
                            cause = execution_result
                            cause_ts = ts

        if cause:
            stdout, stderr = cls._get_logs(cause["id"])
            return {
                "failed_task": cause["id"],
                "failed_task_stdout": stdout,
                "failed_task_stderr": stderr
            }
        else:
            return {
                "msg": f"Analysis {analysis.get_id()} failed but the cause could not "
                       f"be determined"
            }

    @classmethod
    def _get_logs(cls, job_id) -> Tuple[str, ...]:
        logs = ([], [])

        def callback(msg_dict):
            for src, log in zip((STDOUT_LOG, STDERR_LOG), logs):
                if msg_dict["source"] == src:
                    log.append(msg_dict["msg"])
                    break

        client = DXJobLogStreamClient(job_id, msg_callback=callback)
        client.connect()

        return tuple("\n".join(log) for log in logs)

    def _get_analysis_outputs(
        self,
        analysis: dxpy.DXAnalysis,
        expected: Iterable[str],
        default_namespace: str = OUTPUT_STAGE,
    ) -> dict:
        all_outputs = analysis.describe()["output"]
        output = {}

        for key in expected:
            exp_key = key
            if exp_key not in all_outputs and "." not in exp_key:
                exp_key = f"{default_namespace}.{exp_key}"
            if exp_key not in all_outputs:
                raise ValueError(
                    f"Did not find key {exp_key} in outputs of analysis "
                    f"{analysis.get_id()}"
                )
            output[exp_key] = self._resolve_output(all_outputs[exp_key])

        return output

    def _resolve_output(self, value):
        if isinstance(value, str):
            return value
        elif dxpy.is_dxlink(value):
            dxfile = dxpy.DXFile(value)
            file_id = dxfile.get_id()
            if file_id not in DxWdlExecutor._data_cache:
                # Store each file in a subdirectory named by it's ID to avoid
                # naming collisions
                cache_dir = self._dxwdl_cache_dir / file_id
                cache_dir.mkdir(parents=True)
                filename = cache_dir / dxfile.describe()["name"]
                dxpy.download_dxfile(dxfile, filename)
                DxWdlExecutor._data_cache[file_id] = filename
            return DxWdlExecutor._data_cache[file_id]
        elif isinstance(value, dict):
            return {
                key: self._resolve_output(val)
                for key, val in cast(dict, value).items()
            }
        elif isinstance(value, Sequence):
            return [self._resolve_output(val) for val in cast(Sequence, value)]
        else:
            return value


class DxInputsFormatter(InputsFormatter):
    def __init__(
        self,
        project_id: str = dxpy.PROJECT_CONTEXT_ID,
        data_project_id: Optional[str] = None,
        folder: str = "/",
        data_folder: Optional[str] = None,
        **_
    ):
        self._project_id = data_project_id or project_id
        self._folder = data_folder or folder
        self._data_file_links = set()

    def format_inputs(
        self, inputs_dict: dict, namespace: Optional[str] = None, **kwargs
    ) -> dict:
        prefix = f"{namespace}." if namespace else ""
        formatted = {}

        for key, value in inputs_dict.items():
            new_key = f"{prefix}{key}"

            if isinstance(value, dict):
                formatted_dict = self._format_dict(cast(dict, value))
                formatted[new_key] = {DX_STRUCT_KEY: formatted_dict}

                if self._data_file_links:
                    formatted[f"{new_key}{DX_FILES_SUFFIX}"] = list(
                        self._data_file_links
                    )
                    self._data_file_links.clear()
            else:
                formatted[new_key] = super().format_value(value)

        return formatted

    # The following function implements dict -> Map mapping. Since we cannot determine
    # a priori whether a dict should map to a Map or a Struct, we assume Struct and
    # disallow Map-type inputs.
    # def _format_dict(self, d: dict) -> dict:
    #     struct = {"keys": [], "values": []}
    #
    #     for key, val in d.items():
    #         struct["keys"].append(key)
    #         struct["values"].append(self.format_value(val))
    #
    #     return {DX_STRUCT_KEY: struct}

    def _format_data_file(self, df: DataFile) -> dict:
        if isinstance(df.localizer, UrlLocalizer):
            ul = cast(UrlLocalizer, df.localizer)
            if ul.url.startswith("dx://"):
                return dxpy.dxlink(*ul.url[5:].split(":"))

        file_name = df.local_path.name

        existing_files = list(dxpy.find_data_objects(
            classname="file",
            state="closed",
            name=file_name,
            project=self._project_id,
            folder=self._folder,
            recurse=False
        ))

        if not existing_files:
            # TODO: batch uploads and use dxpy.sugar.transfers.Uploader for
            #  parallelization
            return dxpy.dxlink(dxpy.upload_local_file(
                str(df.path),
                name=file_name,
                project=self._project_id,
                folder=self._folder,
                parents=True,
                wait_on_close=True
            ))
        elif len(existing_files) == 1:
            return dxpy.dxlink(existing_files[0]["id"], self._project_id)
        else:
            raise RuntimeError(
                f"Multiple files with name {file_name} found in "
                f"{self._project_id}:{self._folder}"
            )
