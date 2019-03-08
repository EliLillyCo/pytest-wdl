import os
import pytest


@pytest.fixture(scope="module")
def test_data_dir(project_root):
    return os.path.join(project_root, "tests")


def test_fixtures(test_data, cromwell_harness):
    inputs = {
        "in_txt": test_data["in_txt"]
    }
    outputs = {
        "out_txt": test_data["out_txt"]
    }
    cromwell_harness.run_workflow("tests/test.wdl", "cat_file", inputs, outputs)
