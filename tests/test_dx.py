import contextlib
from pathlib import Path
import random
import string
from typing import cast
from urllib.request import urlopen

import pytest
from _pytest.fixtures import FixtureRequest

from pytest_wdl.executors import parse_wdl
from pytest_wdl.plugins import PluginError
from pytest_wdl.url_schemes import Response
from pytest_wdl.utils import tempdir

SKIP_REASON = "dxpy is not installed; DNAnexus URL handler and dxWDL executor will " \
              "not be tested"

try:
    dx = pytest.importorskip("pytest_wdl.providers.dx", reason=SKIP_REASON)
    dxpy = dx.dxpy
    # Force non-interactive login since we may be running in a CI/CD environment
    with dx.login(interactive=False):
        assert dxpy.whoami()
except PluginError as err:
    dxpy = None

pytestmark = pytest.mark.skipif(dxpy is None, reason=SKIP_REASON)


DX_FILE_ID = "file-BgY4VzQ0bvyg22pfZQpXfzgK"
DX_PROJECT_ID = "project-BQbJpBj0bvygyQxgQ1800Jkk"


@contextlib.contextmanager
def random_project_folder(length: int = 8, prefix: str = "") -> str:
    """
    ContextManager that generates a random folder name, ensures that it doesn't
    already exist in the current project, yields it, and then deletes the folder if it
    exists.

    Returns:
        The folder path.
    """
    letters = string.ascii_letters + string.digits
    project = dxpy.DXProject(dxpy.PROJECT_CONTEXT_ID)

    while True:
        folder = "".join(random.choices(letters, k=length))
        folder_path = f"{prefix}{'' if prefix.endswith('/') else '/'}{folder}"
        try:
            project.list_folder(folder_path)
        except dxpy.exceptions.ResourceNotFound:
            # We found a folder that does not exist
            break

    try:
        yield folder_path
    finally:
        project.remove_folder(folder_path, recurse=True, force=True)


def test_dx_scheme():
    rsp = urlopen(f"dx://{DX_FILE_ID}")
    assert isinstance(rsp, Response)
    import pytest_wdl.providers.dx
    assert isinstance(rsp, pytest_wdl.providers.dx.DxResponse)
    with tempdir() as d:
        outfile = d / "readme.txt"
        cast(Response, rsp).download_file(outfile, False)
        assert outfile.exists()
        with open(outfile, "rt") as inp:
            txt = inp.read()
        assert txt.startswith("README.1st.txt")
        assert txt.rstrip().endswith(
            "SRR100022: Full exome to use as input to your analyses."
        )


def test_dx_scheme_with_project():
    rsp = urlopen(f"dx://{DX_PROJECT_ID}:{DX_FILE_ID}")
    assert isinstance(rsp, Response)
    import pytest_wdl.providers.dx
    assert isinstance(rsp, pytest_wdl.providers.dx.DxResponse)
    with tempdir() as d:
        outfile = d / "readme.txt"
        cast(Response, rsp).download_file(outfile, False)
        assert outfile.exists()
        with open(outfile, "rt") as inp:
            txt = inp.read()
        assert txt.startswith("README.1st.txt")
        assert txt.rstrip().endswith(
            "SRR100022: Full exome to use as input to your analyses."
        )


def test_dx_input_formatter(request: FixtureRequest):
    doc = parse_wdl(Path(request.fspath.dirpath()) / "test_dx.wdl")
    dx_input_formatter = dx.DxInputsFormatter(doc)

    assert dx_input_formatter.format_inputs({
        "str": "abc",
        "array_str": ["def", "ghi"],
        "map_str_str": {
            "jkl": "mno"
        },
        "struc": {
            "str": "pqr",
            "array_str": ["stu", "vwx"],
            "map_str_str": {
                "xy1": "234"
            }
        },
        "array_struc": [{
            "str": "567",
            "array_str": ["890", "ABC"],
            "map_str_str": {
                "DEF": "GHI"
            }
        }],
        "map_str_struc": {
            "JKL": {
                "str": "MNO",
                "array_str": ["PQR", "STU"],
                "map_str_str": {
                    "VWX": "YZ1"
                }
            }
        },
        "pair_str_str": {
            "left": "A",
            "right": "B"
        },
        "array_pair_str_str": [
            {
                "left": "X",
                "right": "Y"
            }
        ]
    }) == {
        "str": "abc",
        "array_str": ["def", "ghi"],
        "map_str_str": {
            "___": {
                "keys": ["jkl"],
                "values": ["mno"]
            }
        },
        "struc": {
            "___": {
                "str": "pqr",
                "array_str": ["stu", "vwx"],
                "map_str_str": {
                    "keys": ["xy1"],
                    "values": ["234"]
                }
            }
        },
        "array_struc": {
            "___": [{
                "str": "567",
                "array_str": ["890", "ABC"],
                "map_str_str": {
                    "keys": ["DEF"],
                    "values": ["GHI"]
                }
            }]
        },
        "map_str_struc": {
            "___": {
                "keys": ["JKL"],
                "values": [{
                    "str": "MNO",
                    "array_str": ["PQR", "STU"],
                    "map_str_str": {
                        "keys": ["VWX"],
                        "values": ["YZ1"]
                    }
                }]
            }
        },
        "pair_str_str": {
            "___": {
                "left": "A",
                "right": "B"
            }
        },
        "array_pair_str_str": {
            "___": [
                {
                    "left": "X",
                    "right": "Y"
                }

            ]
        }
    }


def test_dx_input_formatter_with_data_files():
    """TODO"""


@pytest.mark.integration
@pytest.mark.remote
def test_dxwdl_workflow(workflow_data, workflow_runner):
    with random_project_folder() as workflow_folder:
        inputs = {
            "in_txt": workflow_data["in_txt"],
            "in_int": 1
        }
        outputs = {
            "out_txt": workflow_data["out_txt"],
            "out_int": 1
        }
        workflow_runner(
            "test.wdl",
            inputs,
            outputs,
            executors=["dxwdl"],
            workflow_folder=workflow_folder
        )


# TODO: implement task support for dxWDL executor
# @pytest.mark.integration
# @pytest.mark.remote
# def test_dxwdl_task(workflow_data, workflow_runner):
#     with random_project_folder() as workflow_folder:
#         inputs = {
#             "in_txt": workflow_data["in_txt"],
#             "in_int": 1
#         }
#         outputs = {
#             "out_txt": workflow_data["out_txt"],
#             "out_int": 1
#         }
#         workflow_runner(
#             "test.wdl",
#             inputs,
#             outputs,
#             executors=["dxwdl"],
#             task_name="cat",
#             workflow_folder=workflow_folder
#         )
