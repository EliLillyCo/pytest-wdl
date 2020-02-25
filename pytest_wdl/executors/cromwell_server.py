import json
from pathlib import Path
from typing import IO, Optional, Sequence, Union

import requests
from requests.auth import HTTPBasicAuth

from pytest_wdl.executors import (
    Executor,
    ExecutionFailedError,
    get_target_name,
    read_write_inputs,
)
from pytest_wdl.executors._cromwell import CromwellHelperMixin
from pytest_wdl.utils import LOG, PollingException, poll


DEFAULT_API_URL = "http://localhost:8000/api/workflows/v1"
DEFAULT_POLLING_STEP = 5  # seconds
DEFAULT_POLLING_TIMEOUT = 3600  # seconds
TERMINAL_STATES = ["Succeeded", "Aborted", "Failed"]


class CromwellServerExecutor(Executor, CromwellHelperMixin):
    """
    Manages the running of WDL workflows using a remote Cromwell running in Server mode.

    Args:
        import_dirs: Relative or absolute paths to directories containing WDL
            scripts that should be available as imports.
        cromwell_api_url: The full URL where this cromwell exists
            `http://localhost:8000/api/workflows/v1`
        cromwell_api_username: The username to pass to the cromwell API if protected by
            basic auth
        cromwell_api_password: The password to pass to the cromwell API if protected by
            basic auth
        cromwell_configuration: A config file that will be passed to Cromwell
    """

    def __init__(
        self,
        import_dirs: Optional[Sequence[Path]] = None,
        cromwell_api_url: Optional[str] = DEFAULT_API_URL,
        cromwell_api_username: Optional[str] = None,
        cromwell_api_password: Optional[str] = None,
        cromwell_configuration: Optional[Union[str, Path, dict]] = None,
    ):
        self._import_dirs = import_dirs
        self._cromwell_api_url = cromwell_api_url
        self._cromwell_config_file = cromwell_configuration

        if cromwell_api_username and cromwell_api_password:
            self._auth = HTTPBasicAuth(cromwell_api_username, cromwell_api_password)
        else:
            self._auth = None

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

        inputs_dict, _ = read_write_inputs(
            inputs_file=kwargs.get("inputs_file"),
            inputs_dict=inputs,
            namespace=target,
            write_formatted_inputs=False
        )

        payload = {}
        payload_files = []

        def open_payload_file(path: Path, mode: str = "r") -> IO:
            open_file = open(path, mode)
            payload_files.append(open_file)
            return open_file

        try:
            payload["workflowSource"] = open_payload_file(wdl_path)

            if inputs_dict:
                payload["workflowInputs"] = json.dumps(inputs_dict, default=str)

            imports_file = self._get_workflow_imports(
                self._import_dirs, kwargs.get("imports_file")
            )

            if imports_file:
                payload["workflowDependencies"] = open_payload_file(imports_file, "rb")

            if self._cromwell_config_file:
                if isinstance(inputs_dict, dict):
                    payload["workflowOptions"] = json.dumps(
                        self._cromwell_config_file, default=str
                    )
                else:
                    payload["workflowOptions"] = open_payload_file(
                        self._cromwell_config_file
                    )

            LOG.info(
                f"Executing cromwell server '{self._cromwell_api_url}' with inputs "
                f"{json.dumps(inputs_dict, default=str)}"
            )

            with requests.post(
                self._cromwell_api_url, files=payload, auth=self._auth
            ) as resp:
                status_object = self._resp_to_json(resp, target, inputs_dict)
                run_id = status_object["id"]
                LOG.info(
                    f"Executing on cromwell with id {run_id}. Waiting until terminal "
                    f"state is reached"
                )
        finally:
            for fh in payload_files:
                try:
                    fh.close()
                except:
                    LOG.exception("Error closing file %s", fh)

        self._poll_until_terminal(
            run_id, target, inputs_dict, kwargs.get("timeout", DEFAULT_POLLING_TIMEOUT)
        )

        metadata_url = f"{self._cromwell_api_url}/{run_id}/metadata"
        outputs = None

        with requests.get(metadata_url, auth=self._auth) as metadata_response:
            metadata = self._resp_to_json(metadata_response, target, inputs_dict)

            if metadata["status"] == "Succeeded":
                outputs = metadata["outputs"]
            else:
                error_kwargs = {
                    "executor": "cromwell",
                    "target": target,
                    "status": "Failed",
                    "inputs": inputs_dict,
                }
                self._parse_metadata_errors(
                    metadata, target=target, error_kwargs=error_kwargs
                )
                raise ExecutionFailedError(**error_kwargs)

        if expected:
            self._validate_outputs(outputs, expected, target)

        return outputs

    @staticmethod
    def _resp_to_json(resp, target=None, inputs_dict=None):
        if resp.ok:
            return resp.json()
        else:
            error_kwargs = {
                "executor": "cromwell-server",
                "target": target,
                "status": "Failed",
                "inputs": inputs_dict,
            }

            if resp.reason:
                error_kwargs["msg"] = resp.reason

            raise ExecutionFailedError(**error_kwargs)

    def _poll_until_terminal(
        self,
        run_id: str,
        target: str,
        inputs_dict: Optional[dict] = None,
        timeout: int = DEFAULT_POLLING_TIMEOUT
    ):
        def get_status(status_url):
            with requests.get(status_url, auth=self._auth) as rsp:
                status_dict = self._resp_to_json(rsp, target, inputs_dict)
                return status_dict.get("status") in TERMINAL_STATES

        try:
            poll(
                get_status,
                args=(f"{self._cromwell_api_url}/{run_id}/status",),
                step=DEFAULT_POLLING_STEP,
                timeout=timeout
            )
        except PollingException:
            LOG.exception(f"Encountered timeout for run with id {run_id}")

            error_kwargs = {
                "executor": "cromwell-server",
                "target": target,
                "status": "Failed",
                "inputs": inputs_dict,
                "msg": f"Encountered timeout for run with id {run_id}",
            }

            raise ExecutionFailedError(**error_kwargs)
