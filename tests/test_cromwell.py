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

import json
from pathlib import Path
import zipfile

from pytest_wdl.utils import tempdir
import pytest

from pytest_wdl.utils import ENV_PATH, ENV_CLASSPATH
from pytest_wdl.executors.cromwell import (
    ENV_CROMWELL_CONFIG, ENV_JAVA_HOME, ENV_CROMWELL_JAR, CromwellExecutor, Failures
)
from . import setenv, make_executable


def test_java_bin():
    with tempdir() as d:
        java = d / "bin" / "java"
        java.parent.mkdir(parents=True)
        with open(java, "wt") as out:
            out.write("foo")
        make_executable(java)

        with setenv({ENV_JAVA_HOME: str(d)}):
            assert CromwellExecutor([d]).java_bin == java

        with setenv({
            ENV_PATH: str(d / "bin"),
            ENV_JAVA_HOME: None
        }):
            assert CromwellExecutor([d]).java_bin == java

        with setenv({
            ENV_PATH: None,
            ENV_JAVA_HOME: None
        }):
            with pytest.raises(FileNotFoundError):
                assert CromwellExecutor([d]).java_bin

    with setenv({ENV_JAVA_HOME: "foo"}):
        with pytest.raises(FileNotFoundError):
            assert CromwellExecutor([d]).java_bin


def test_cromwell_config():
    with tempdir() as d:
        assert CromwellExecutor([d]).cromwell_config_file is None
        config = d / "config"
        with setenv({ENV_CROMWELL_CONFIG: str(config)}):
            with pytest.raises(FileNotFoundError):
                CromwellExecutor([d])
            with open(config, "wt") as out:
                out.write("foo")
            assert CromwellExecutor([d]).cromwell_config_file == config


def test_java_args():
    with tempdir() as d:
        assert CromwellExecutor([d]).java_args is None

        with pytest.raises(FileNotFoundError):
            CromwellExecutor([d], cromwell_config_file=Path("foo")).java_args

        config = d / "config"
        with pytest.raises(FileNotFoundError):
            CromwellExecutor([d], cromwell_config_file=Path("foo")).java_args
        with open(config, "wt") as out:
            out.write("foo")
        assert CromwellExecutor(
            [d], cromwell_config_file=config
        ).java_args == f"-Dconfig.file={config}"


def test_cromwell_jar():
    with tempdir() as d:
        jar = d / "cromwell.jar"

        with setenv({ENV_CROMWELL_JAR: str(jar)}):
            with pytest.raises(FileNotFoundError):
                CromwellExecutor([d]).cromwell_jar_file
            with open(jar, "wt") as out:
                out.write("foo")
            assert CromwellExecutor([d]).cromwell_jar_file == jar

        with setenv({
            ENV_CROMWELL_JAR: None,
            ENV_CLASSPATH: str(d)
        }):
            assert CromwellExecutor([d]).cromwell_jar_file == jar

        with setenv({
            ENV_CROMWELL_JAR: None,
            ENV_CLASSPATH: str(jar)
        }):
            assert CromwellExecutor([d]).cromwell_jar_file == jar

        with setenv({
            ENV_CROMWELL_JAR: None,
            ENV_CLASSPATH: None
        }):
            with pytest.raises(FileNotFoundError):
                CromwellExecutor([d]).cromwell_jar_file


def test_get_workflow_imports():
    with tempdir() as d:
        wdl_dir = d / "foo"
        wdl = wdl_dir / "bar.wdl"
        wdl_dir.mkdir()
        with open(wdl, "wt") as out:
            out.write("foo")
        executor = CromwellExecutor([wdl_dir])
        zip_path = executor.get_workflow_imports()
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as import_zip:
            names = import_zip.namelist()
            assert len(names) == 1
            assert names[0] == "bar.wdl"
            with import_zip.open("bar.wdl", "r") as inp:
                assert inp.read().decode() == "foo"

    with tempdir() as d:
        wdl_dir = d / "foo"
        wdl = wdl_dir / "bar.wdl"
        wdl_dir.mkdir()
        with open(wdl, "wt") as out:
            out.write("foo")
        imports_file = d / "imports.zip"
        executor = CromwellExecutor([wdl_dir])
        zip_path = executor.get_workflow_imports(imports_file)
        assert zip_path.exists()
        assert zip_path == imports_file
        with zipfile.ZipFile(zip_path, "r") as import_zip:
            names = import_zip.namelist()
            assert len(names) == 1
            assert names[0] == "bar.wdl"
            with import_zip.open("bar.wdl", "r") as inp:
                assert inp.read().decode() == "foo"

    with tempdir() as d:
        wdl_dir = d / "foo"
        wdl = wdl_dir / "bar.wdl"
        wdl_dir.mkdir()
        with open(wdl, "wt") as out:
            out.write("foo")
        imports_file = d / "imports.zip"
        with open(imports_file, "wt") as out:
            out.write("foo")
        executor = CromwellExecutor()
        zip_path = executor.get_workflow_imports(imports_file=imports_file)
        assert zip_path.exists()
        assert zip_path == imports_file


def test_failure_metadata(workflow_data):
    m44 = workflow_data["metadata44.json"]
    with open(m44.path, "rt") as inp:
        m44_dict = json.load(inp)
    failures = CromwellExecutor.get_failures(m44_dict)
    assert failures.num_failed == 10
    assert failures.failed_task == "contam_testing_set_org_by_volume.org_blast"
    assert failures.failed_task_exit_status == "Unknown"
    assert "6717f340-b948-4e97-ac2c-bdba793893f5" in \
           str(failures._failed_task_stdout_path)
    assert "6717f340-b948-4e97-ac2c-bdba793893f5" in \
           str(failures._failed_task_stderr_path)

    m47 = workflow_data["metadata47.json"]
    with open(m47.path, "rt") as inp:
        m47_dict = json.load(inp)
    failures = CromwellExecutor.get_failures(m47_dict)
    assert failures.num_failed == 10
    assert failures.failed_task == "contam_testing_set_org_by_volume.org_blast"
    assert failures.failed_task_exit_status == "Unknown"
    assert "563012ef-e593-42dc-9de0-f0a682ce23e3" in \
           str(failures._failed_task_stdout_path)
    assert "563012ef-e593-42dc-9de0-f0a682ce23e3" in \
           str(failures._failed_task_stderr_path)


def test_call_failure_metadata(workflow_data):
    m = workflow_data["metadata_call_failed.json"]
    with open(m.path, "rt") as inp:
        m_dict = json.load(inp)
    failures = CromwellExecutor.get_failures(m_dict)
    assert failures.num_failed == 1
    assert failures.failed_task == "ScatterAt27_14"
    assert failures.failed_task_exit_status == "Unknown"
    assert "Failed to evaluate inputs for sub workflow" in failures._failed_task_stderr
