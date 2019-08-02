from pathlib import Path
from pytest_cromwell.fixtures import import_dirs, java_bin
from pytest_cromwell.utils import tempdir
import pytest
from . import setenv, make_executable
from unittest.mock import Mock


def test_fixtures(test_data, workflow_runner):
    inputs = {
        "in_txt": test_data["in_txt"]
    }
    outputs = {
        "out_txt": test_data["out_txt"]
    }
    workflow_runner("tests/test.wdl", "cat_file", inputs, outputs)


def test_import_dirs():
    with pytest.raises(FileNotFoundError):
        import_dirs(None, Path.cwd(), "foo")

    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("bar")
        with pytest.raises(FileNotFoundError):
            import_dirs(None, d, "foo")

    cwd = Path.cwd()
    mock = Mock()
    mock.fspath.dirpath.return_value = cwd
    assert import_dirs(mock, None, None) == [cwd.parent]


def test_java_bin():
    with tempdir() as d:
        java = d / "bin" / "java"
        java.parent.mkdir(parents=True)
        with open(java, "wt") as out:
            out.write("foo")
        make_executable(java)

        with setenv({"JAVA_HOME": str(d)}):
            assert java_bin() == java

        with setenv({
            "PATH": str(d / "bin"),
            "JAVA_HOME": None
        }):
            assert java_bin() == java

    with setenv({"JAVA_HOME": "foo"}):
        with pytest.raises(FileNotFoundError):
            java_bin()
