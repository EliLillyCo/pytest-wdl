from pathlib import Path
from pytest_wdl.fixtures import (
    import_dirs, java_bin, cromwell_config_file, java_args, cromwell_jar_file
)
from pytest_wdl.utils import tempdir
import pytest
from unittest.mock import Mock
from . import setenv, make_executable


def test_fixtures(io_data, workflow_runner):
    inputs = {
        "in_txt": io_data["in_txt"]
    }
    outputs = {
        "out_txt": io_data["out_txt"]
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
            import_dirs(None, d, foo)

    with tempdir(change_dir=True) as cwd:
        tests = cwd / "tests"
        tests.mkdir()
        req = Mock()
        req.fspath.dirpath.return_value = str(tests)

        assert import_dirs(req, None, None) == []

        foo = cwd / "foo.wdl"
        with open(foo, "wt") as out:
            out.write("foo")
        assert import_dirs(req, None, None) == [cwd]


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

        with setenv({
            "PATH": None,
            "JAVA_HOME": None
        }):
            with pytest.raises(FileNotFoundError):
                java_bin()

    with setenv({"JAVA_HOME": "foo"}):
        with pytest.raises(FileNotFoundError):
            java_bin()


def test_cromwell_config():
    assert cromwell_config_file() is None
    with tempdir() as d:
        config = d / "config"
        with setenv({"CROMWELL_CONFIG_FILE": str(config)}):
            with pytest.raises(FileNotFoundError):
                cromwell_config_file()
            with open(config, "wt") as out:
                out.write("foo")
            assert cromwell_config_file() == config


def test_java_args():
    assert java_args(None) is None
    with pytest.raises(FileNotFoundError):
        java_args(Path("foo"))
    with tempdir() as d:
        config = d / "config"
        with pytest.raises(FileNotFoundError):
            java_args(config)
        with open(config, "wt") as out:
            out.write("foo")
        assert java_args(config) == f"-Dconfig.file={config}"


def test_cromwell_jar():
    with tempdir() as d:
        jar = d / "cromwell.jar"

        with setenv({"CROMWELL_JAR": str(jar)}):
            with pytest.raises(FileNotFoundError):
                cromwell_jar_file()
            with open(jar, "wt") as out:
                out.write("foo")
            assert cromwell_jar_file() == jar

        with setenv({
            "CROMWELL_JAR": None,
            "CLASSPATH": str(d)
        }):
            assert cromwell_jar_file() == jar

        with setenv({
            "CROMWELL_JAR": None,
            "CLASSPATH": str(jar)
        }):
            assert cromwell_jar_file() == jar

        with setenv({
            "CROMWELL_JAR": None,
            "CLASSPATH": None
        }):
            with pytest.raises(FileNotFoundError):
                cromwell_jar_file()
