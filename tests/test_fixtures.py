from pathlib import Path
import pytest


def test_fixtures(test_data, workflow_runner):
    inputs = {
        "in_txt": test_data["in_txt"]
    }
    outputs = {
        "out_txt": test_data["out_txt"]
    }
    workflow_runner("tests/test.wdl", "cat_file", inputs, outputs)
