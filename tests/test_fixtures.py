import os
import pytest


@pytest.fixture(scope="module")
def project_root(request):
    return os.path.abspath(os.path.join(os.path.dirname(request.fspath), ".."))


def test_fixtures(test_data_ng, workflow_runner):
    inputs = {
        "in_txt": test_data_ng["in_txt"]
    }
    outputs = {
        "out_txt": test_data_ng["out_txt"]
    }
    workflow_runner("tests/test.wdl", "cat_file", inputs, outputs)
