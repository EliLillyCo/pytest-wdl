from pathlib import Path
from typing import Optional, Union

from pytest_wdl.executors import (
    ExecutionFailedError, Executor, get_workflow_inputs, validate_outputs
)


class DxWdlEexecutor(Executor):
    def run_workflow(
        self,
        wdl_path: Union[str, Path],
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs
    ) -> dict:
        pass
