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
from argparse import Namespace
import contextlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union, cast
from unittest.mock import patch

import dxpy
from dxpy.scripts import dx
from dxpy.utils.job_log_client import DXJobLogStreamClient
import subby

from pytest_wdl import config
from pytest_wdl.data_types import DataFile
from pytest_wdl.executors import ExecutionFailedError, JavaExecutor
from pytest_wdl.localizers import UrlLocalizer
from pytest_wdl.url_schemes import Method, Request, Response, UrlHandler
from pytest_wdl.utils import LOG, ensure_path, verify_digests


ENV_JAVA_HOME = "JAVA_HOME"
ENV_DXWDL_JAR = "DXWDL_JAR"


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
        conf = config.get_instance().get_executor_defaults("dxwdl")
        username = conf.get("username")
        token = conf.get("token")
        if "DX_USERNAME" not in os.environ and username:
            os.environ["DX_USERNAME"] = username
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
        **defaults
    ):
        super().__init__(import_dirs, java_bin, java_args)
        self.dxwdl_jar_file = JavaExecutor.resolve_jar_file(
            "dxWDL*.jar", dxwdl_jar_file, ENV_DXWDL_JAR
        )
        if dxwdl_cache_dir:
            self.dxwdl_cache_dir = ensure_path(dxwdl_cache_dir)
            self._cleanup_cache = False
        else:
            self.dxwdl_cache_dir = ensure_path(tempfile.mkdtemp())
            self._cleanup_cache = True
        self.defaults = defaults

    def run_workflow(
        self,
        wdl_path: Path,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs
    ) -> dict:
        def get_arg(name: str, default=None):
            return kwargs.get(name) or self.defaults.get(name) or default

        cls = self.__class__
        workflow_name = self._get_workflow_name(wdl_path, kwargs)
        namespace = get_arg("stage_id", "stage-common")
        inputs_file = kwargs.get("inputs_file")
        inputs_dict = None

        if inputs_file:
            inputs_dict, inputs_file = cls._read_inputs(inputs_file)

        if not inputs_dict:
            project_id = (
                get_arg("data_project_id") or
                get_arg("project_id", dxpy.PROJECT_CONTEXT_ID)
            )
            folder = get_arg("data_folder") or get_arg("folder", "/")
            inputs_dict = JavaExecutor._format_inputs(inputs_dict, namespace, False)
            cls._resolve_data_files(inputs, project_id, folder)

        with login():
            workflow = self._resolve_workflow(wdl_path, workflow_name, kwargs)
            analysis = workflow.run(inputs_dict)

            try:
                analysis.wait_on_done()
                outputs = self._get_analysis_outputs(analysis, expected.keys(), namespace)
                if expected:
                    cls._validate_outputs(outputs, expected, workflow_name)
                return outputs
            except dxpy.exceptions.DXJobFailureError:
                raise ExecutionFailedError(
                    "dxWDL",
                    workflow_name,
                    analysis.describe()["state"],
                    inputs_dict,
                    **cls._get_failed_task(analysis)
                )
            finally:
                if self._cleanup_cache:
                    shutil.rmtree(self.dxwdl_cache_dir)

    def _resolve_workflow(
        self, wdl_path: Path, workflow_name: str, kwargs: dict
    ) -> dxpy.DXWorkflow:
        def get_arg(name: str, default=None):
            return kwargs.get(name) or self.defaults.get(name) or default

        if wdl_path in DxWdlExecutor._workflow_cache:
            return DxWdlExecutor._workflow_cache[wdl_path]

        project_id = (
            get_arg("workflow_project_id") or
            get_arg("project_id", dxpy.PROJECT_CONTEXT_ID)
        )
        folder = get_arg("workflow_folder") or get_arg("folder", "/")
        build_workflow = get_arg("force", False)
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

            if existing_workflow:
                created = existing_workflow[0]["describe"]["created"]
                if wdl_path.stat().st_mtime > created:
                    build_workflow = True
                elif self.import_dirs:
                    for import_dir in self.import_dirs:
                        for imp in import_dir.glob("*.wdl"):
                            if imp.stat().st_mtime > created:
                                build_workflow = True
                                break
                    else:
                        workflow_id = existing_workflow[0]["id"]

        if build_workflow:
            extras = get_arg("extras")
            extras_arg = f"-extras {extras}" if extras else ""
            archive = get_arg("archive")
            archive_arg = "-a" if archive else "-f"
            imports_args = " ".join(f"-imports {d}" for d in self.import_dirs)
            cmd = (
                f"{self.java_bin} {self.java_args} -jar {self.dxwdl_jar_file} compile "
                f"{wdl_path} -destination {project_id}:{folder} {imports_args} "
                f"{extras_arg} {archive_arg}"
            )
            LOG.info(f"Building workflow with command '{cmd}'")
            workflow_id = subby.sub(cmd).splitlines(False)[-1]

        workflow = dxpy.DXWorkflow(workflow_id)
        DxWdlExecutor._workflow_cache[wdl_path] = workflow
        return workflow

    @classmethod
    def _resolve_data_files(cls, inputs_dict: dict, project_id: str, folder: str):
        def handle_data_files(
            obj, _file_links: Optional[List] = None
        ) -> Optional[List]:
            """
            Go through the input hierarchy, find all data files, and:
            1. Upload any data that does not already exist on DNAnexus
            2. Add ___dxfiles inputs
            """
            if isinstance(obj, str):
                pass
            if isinstance(obj, dict):
                for value in cast(dict, obj).values():
                    handle_data_files(value, _file_links)
            elif isinstance(obj, Sequence):
                for value in cast(Sequence, obj):
                    handle_data_files(value, _file_links)
            elif isinstance(obj, DataFile):
                df = cast(DataFile, obj)
                dxlink = None

                if isinstance(df.localizer, UrlLocalizer):
                    ul = cast(UrlLocalizer, df.localizer)
                    if ul.url.startswith("dx://"):
                        dxlink = dxpy.dxlink(*ul.url[5:].split(":"))

                if dxlink is None:
                    file_name = df.local_path.name
                    existing_files = list(dxpy.find_data_objects(
                        classname="file",
                        state="closed",
                        name=file_name,
                        project=project_id,
                        folder=folder,
                        recurse=False
                    ))
                    if not existing_files:
                        dxlink = dxpy.dxlink(dxpy.upload_local_file(
                            str(df.path),
                            name=file_name,
                            project=project_id,
                            folder=folder,
                            wait_on_close=True
                        ))
                    elif len(existing_files) == 1:
                        dxlink = dxpy.dxlink(existing_files[0]["id"], project_id)
                    else:
                        raise RuntimeError(
                            f"Multiple files with name {file_name} found in "
                            f"{project_id}:{folder}"
                        )

                _file_links.append(dxlink)

            return _file_links

        for key in list(inputs_dict.keys()):
            file_links = handle_data_files(inputs_dict, [])
            if file_links:
                inputs_dict[f"{key}___dxfiles"] = file_links

        return inputs_dict

    @classmethod
    def _get_failed_task(cls, analysis: dxpy.DXAnalysis) -> dict:
        """
        Find the causal failuree within an execution tree and get the logs.
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
            for src, log in zip(("STDOUT", "STDERR"), logs):
                if msg_dict["source"] == src:
                    log.append(msg_dict["msg"])
                    break

        client = DXJobLogStreamClient(job_id, callback)
        client.connect()

        return tuple("\n".join(log) for log in logs)

    def _get_analysis_outputs(
        self, analysis: dxpy.DXAnalysis, expected: Iterable[str], default_namespace: str
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
            output[key] = self._resolve_output(all_outputs[exp_key])

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
                cache_dir = self.dxwdl_cache_dir / file_id
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
