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

from pathlib import Path
from pytest_wdl.fixtures import (
    ENV_USER_CONFIG, DEFAULT_USER_CONFIG_FILE, import_dirs, user_config_file
)
from pytest_wdl.utils import tempdir
import pytest
from . import setenv, mock_request


def test_user_config_file():
    with tempdir() as d:
        config = d / "config.json"
        with setenv({ENV_USER_CONFIG: config}):
            with pytest.raises(FileNotFoundError):
                user_config_file()
            with open(config, "wt") as out:
                out.write("foo")
            assert user_config_file() == config

    with tempdir() as d, setenv({"HOME": str(d)}):
        config = d / DEFAULT_USER_CONFIG_FILE
        with open(config, "wt") as out:
            out.write("foo")
        assert user_config_file() == config


@pytest.mark.integration
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
    cwd = Path.cwd()
    req = mock_request(cwd)

    with pytest.raises(FileNotFoundError):
        import_dirs(req, cwd, "foo")

    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("bar")
        with pytest.raises(FileNotFoundError):
            import_dirs(req, d, foo)

    with tempdir(change_dir=True) as tmp_cwd:
        tests = tmp_cwd / "tests"
        tests.mkdir()
        assert import_dirs(req, None, None) == [cwd]

    with tempdir(change_dir=True) as tmp_cwd:
        assert import_dirs(mock_request(tmp_cwd), None, None) == []
