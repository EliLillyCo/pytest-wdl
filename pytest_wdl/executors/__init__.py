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
import tempfile
from typing import List, Optional, Tuple, Union

import delegator

from pytest_wdl.core import DataFile
from pytest_wdl.utils import LOG, ensure_path, safe_string


def get_workflow(
    project_root: Path, wdl_file: Union[str, Path], workflow_name: Optional[str] = None
) -> Tuple[Path, str]:
    """
    Resolve the WDL file and workflow name.

    TODO: if `workflow_name` is None, parse the WDL file and extract the name
     of the workflow.

    Args:
        project_root: The root directory to which `wdl_file` might be relative.
        wdl_file: Path to the WDL file.
        workflow_name: The workflow name; if None, the filename without ".wdl"
            extension is used.

    Returns:
        A tuple (wdl_path, workflow_name)
    """
    wdl_path = ensure_path(wdl_file, project_root, canonicalize=True)
    if not wdl_path.exists():
        raise FileNotFoundError(f"WDL file not found at path {wdl_path}")

    if not workflow_name:
        workflow_name = safe_string(wdl_path.stem)

    return wdl_path, workflow_name


def get_workflow_inputs(
    workflow_name: str, inputs_dict: Optional[dict] = None,
    inputs_file: Optional[Path] = None
) -> Tuple[dict, Path]:
    """
    Persist workflow inputs to a file, or load workflow inputs from a file.

    Args:
        workflow_name: Name of the workflow; used to prefix the input parameters when
            creating the inputs file from the inputs dict.
        inputs_dict: Dict of input names/values.
        inputs_file: JSON file with workflow inputs.

    Returns:
        A tuple (inputs_dict, inputs_file)
    """
    if inputs_file:
        inputs_file = ensure_path(inputs_file)
        if inputs_file.exists():
            with open(inputs_file, "rt") as inp:
                inputs_dict = json.load(inp)
                return inputs_dict, inputs_file

    if inputs_dict:
        inputs_dict = dict(
            (
                f"{workflow_name}.{key}",
                value.path if isinstance(value, DataFile) else value
            )
            for key, value in inputs_dict.items()
        )

        if inputs_file:
            inputs_file = ensure_path(inputs_file, is_file=True, create=True)
        else:
            inputs_file = Path(tempfile.mkstemp(suffix=".json")[1])

        with open(inputs_file, "wt") as out:
            json.dump(inputs_dict, out, default=str)

    return inputs_dict, inputs_file


def get_workflow_imports(
    import_dirs: Optional[List[Path]] = None, imports_file: Optional[Path] = None
) -> Path:
    """
    Creates a ZIP file with all WDL files to be imported.

    Args:
        import_dirs: Directories from which to import WDL files.
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
            wdl
            for path in import_dirs
            for wdl in glob.glob(str(path / "*.wdl"))
        ]
        if imports:
            if imports_path:
                ensure_path(imports_path, is_file=True, create=True)
            else:
                imports_path = Path(tempfile.mkstemp(suffix=".zip")[1])

            imports_str = " ".join(imports)

            LOG.info(f"Writing imports {imports_str} to zip file {imports_path}")
            exe = delegator.run(
                f"zip -j - {imports_str} > {imports_path}", block=True
            )
            if not exe.ok:
                raise Exception(
                    f"Error creating imports zip file; stdout={exe.out}; "
                    f"stderr={exe.err}"
                )

    return imports_path
