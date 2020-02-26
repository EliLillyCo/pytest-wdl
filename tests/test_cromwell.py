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
import os
from pathlib import Path
import zipfile

from pytest_wdl.utils import tempdir
import pytest

from pytest_wdl.utils import ENV_PATH, ENV_CLASSPATH
from pytest_wdl.executors import ENV_JAVA_HOME
from pytest_wdl.executors.cromwell_local import (
    ENV_CROMWELL_CONFIG, ENV_CROMWELL_JAR,  CromwellLocalExecutor
)
from . import setenv, make_executable


def test_java_bin(user_config):
    cromwell_jar_file = user_config.get_executor_defaults("cromwell").get(
        "cromwell_jar_file", os.environ.get(ENV_CROMWELL_JAR)
    )

    with tempdir() as d:
        java = d / "bin" / "java"
        java.parent.mkdir(parents=True)
        with open(java, "wt") as out:
            out.write("foo")
        make_executable(java)

        with setenv({ENV_JAVA_HOME: str(d)}):
            assert  CromwellLocalExecutor(
                [d], cromwell_jar_file=cromwell_jar_file
            ).java_bin == java

        with setenv({
            ENV_PATH: str(d / "bin"),
            ENV_JAVA_HOME: None
        }):
            assert  CromwellLocalExecutor(
                [d], cromwell_jar_file=cromwell_jar_file
            ).java_bin == java

        with setenv({
            ENV_PATH: None,
            ENV_JAVA_HOME: None
        }):
            with pytest.raises(FileNotFoundError):
                assert  CromwellLocalExecutor(
                    [d], cromwell_jar_file=cromwell_jar_file
                ).java_bin

    with setenv({ENV_JAVA_HOME: "foo"}):
        with pytest.raises(FileNotFoundError):
            assert  CromwellLocalExecutor([d]).java_bin


def test_cromwell_config(user_config):
    cromwell_jar_file = user_config.get_executor_defaults("cromwell").get(
        "cromwell_jar_file", os.environ.get(ENV_CROMWELL_JAR)
    )

    with tempdir() as d:
        executor = CromwellLocalExecutor([d], cromwell_jar_file=cromwell_jar_file)
        assert executor._cromwell_args is None
        assert executor.java_args is None

        config = d / "config"
        with setenv({ENV_CROMWELL_CONFIG: str(config)}):
            with pytest.raises(FileNotFoundError):
                 CromwellLocalExecutor([d], cromwell_jar_file=cromwell_jar_file)
            with open(config, "wt") as out:
                out.write("foo")
            executor =  CromwellLocalExecutor(
                [d], cromwell_jar_file=cromwell_jar_file
            )
            assert executor._cromwell_args is None
            assert executor.java_args == f"-Dconfig.file={config}"


def test_java_args(user_config):
    cromwell_jar_file = user_config.get_executor_defaults("cromwell").get(
        "cromwell_jar_file", os.environ.get(ENV_CROMWELL_JAR)
    )

    with tempdir() as d:
        assert  CromwellLocalExecutor(
            [d], cromwell_jar_file=cromwell_jar_file
        ).java_args is None

        with pytest.raises(FileNotFoundError):
             CromwellLocalExecutor(
                [d],
                cromwell_configuration=Path("foo"),
                cromwell_jar_file=cromwell_jar_file
            ).java_args

        config = d / "config"
        with pytest.raises(FileNotFoundError):
             CromwellLocalExecutor(
                [d],
                cromwell_configuration=Path("foo"),
                cromwell_jar_file=cromwell_jar_file,
            ).java_args
        with open(config, "wt") as out:
            out.write("foo")
        assert  CromwellLocalExecutor(
            [d], cromwell_configuration=config, cromwell_jar_file=cromwell_jar_file
        ).java_args == f"-Dconfig.file={config}"


def test_cromwell_jar():
    with tempdir() as d:
        jar = d / "cromwell.jar"

        with setenv({ENV_CROMWELL_JAR: str(jar)}):
            with pytest.raises(FileNotFoundError):
                 CromwellLocalExecutor([d])._cromwell_jar_file
            with open(jar, "wt") as out:
                out.write("foo")
            assert  CromwellLocalExecutor([d])._cromwell_jar_file == jar

        with setenv({
            ENV_CROMWELL_JAR: None,
            ENV_CLASSPATH: str(d)
        }):
            assert  CromwellLocalExecutor([d])._cromwell_jar_file == jar

        with setenv({
            ENV_CROMWELL_JAR: None,
            ENV_CLASSPATH: str(jar)
        }):
            assert  CromwellLocalExecutor([d])._cromwell_jar_file == jar

        with setenv({
            ENV_CROMWELL_JAR: None,
            ENV_CLASSPATH: None
        }):
            with pytest.raises(FileNotFoundError):
                 CromwellLocalExecutor([d])._cromwell_jar_file


def test_get_workflow_imports(user_config):
    cromwell_config = user_config.get_executor_defaults("cromwell")

    with tempdir() as d:
        wdl_dir = d / "foo"
        wdl = wdl_dir / "bar.wdl"
        wdl_dir.mkdir()
        with open(wdl, "wt") as out:
            out.write("foo")
        zip_path =  CromwellLocalExecutor._get_workflow_imports([wdl_dir])
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
        zip_path =  CromwellLocalExecutor._get_workflow_imports(import_dirs=[wdl_dir], imports_file=imports_file)
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
        zip_path =  CromwellLocalExecutor._get_workflow_imports(imports_file=imports_file)
        assert zip_path.exists()
        assert zip_path == imports_file


def test_failure_metadata(workflow_data):
    m44 = workflow_data["metadata44.json"]
    with open(m44.path, "rt") as inp:
        m44_dict = json.load(inp)
    failures =  CromwellLocalExecutor._get_failures(m44_dict)
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
    failures =  CromwellLocalExecutor._get_failures(m47_dict)
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
    failures =  CromwellLocalExecutor._get_failures(m_dict)
    assert failures.num_failed == 1
    assert failures.failed_task == "ScatterAt27_14"
    assert failures.failed_task_exit_status == "Unknown"
    assert "Failed to evaluate inputs for sub workflow" in failures._failed_task_stderr
