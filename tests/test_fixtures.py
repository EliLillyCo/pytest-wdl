from pathlib import Path
from pytest_wdl.fixtures import import_dirs
from pytest_wdl.utils import tempdir
import pytest
from unittest.mock import Mock


def test_fixtures(workflow_data, workflow_runner):
    inputs = {
        "in_txt": workflow_data["in_txt"],
        "in_int": 1
    }
    outputs = {
        "out_txt": workflow_data["out_txt"],
        "out_int": 1
    }
    workflow_runner("tests/test.wdl", "cat_file", inputs, outputs)


def test_import_dirs():
    with pytest.raises(FileNotFoundError):
        import_dirs(Path.cwd(), "foo")

    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("bar")
        with pytest.raises(FileNotFoundError):
            import_dirs(d, foo)

    with tempdir(change_dir=True) as cwd:
        tests = cwd / "tests"
        tests.mkdir()
        assert import_dirs(None, None) == []
