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
import zipfile

from pytest_wdl.utils import tempdir
import pytest

from pytest_wdl.core import DataFile
from pytest_wdl.executors import (
    get_workflow, get_workflow_imports, get_workflow_inputs, make_serializable
)


def test_get_workflow():
    with tempdir() as d:
        wdl = d / "test.wdl"
        with pytest.raises(FileNotFoundError):
            get_workflow([d], "test.wdl")
        with open(wdl, "wt") as out:
            out.write("workflow test {}")
        assert get_workflow([d], "test.wdl") == (wdl, "test")
        assert get_workflow([d], "test.wdl", "foo") == (wdl, "foo")


def test_get_workflow_inputs():
    actual_inputs_dict, inputs_path = get_workflow_inputs(
        {"bar": 1}, namespace="foo"
    )
    assert inputs_path.exists()
    with open(inputs_path, "rt") as inp:
        assert json.load(inp) == actual_inputs_dict
    assert actual_inputs_dict == {
        "foo.bar": 1
    }

    with tempdir() as d:
        inputs_file = d / "inputs.json"
        actual_inputs_dict, inputs_path = get_workflow_inputs(
            {"bar": 1}, inputs_file, "foo"
        )
        assert inputs_file == inputs_path
        assert inputs_path.exists()
        with open(inputs_path, "rt") as inp:
            assert json.load(inp) == actual_inputs_dict
        assert actual_inputs_dict == {
            "foo.bar": 1
        }

    with tempdir() as d:
        inputs_file = d / "inputs.json"
        inputs_dict = {"foo.bar": 1}
        with open(inputs_file, "wt") as out:
            json.dump(inputs_dict, out)
        actual_inputs_dict, inputs_path = get_workflow_inputs(
            inputs_file=inputs_file, namespace="foo"
        )
        assert inputs_file == inputs_path
        assert inputs_path.exists()
        with open(inputs_path, "rt") as inp:
            assert json.load(inp) == actual_inputs_dict
        assert actual_inputs_dict == inputs_dict


def test_get_workflow_imports():
    with tempdir() as d:
        wdl_dir = d / "foo"
        wdl = wdl_dir / "bar.wdl"
        wdl_dir.mkdir()
        with open(wdl, "wt") as out:
            out.write("foo")
        zip_path = get_workflow_imports([wdl_dir])
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
        zip_path = get_workflow_imports([wdl_dir], imports_file)
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
        zip_path = get_workflow_imports(imports_file=imports_file)
        assert zip_path.exists()
        assert zip_path == imports_file


def test_make_serializable():
    assert make_serializable(1) == 1
    assert make_serializable("foo") == "foo"
    assert make_serializable((1.1, 2.2)) == [1.1, 2.2]

    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("foo")
        df = DataFile(foo)
        assert make_serializable(df) == foo
        assert make_serializable([df]) == [foo]
        assert make_serializable({"a": df}) == {"a": foo}

    class Obj:
        def __init__(self, a: str, b: int):
            self.a = a
            self.b = b

        def as_dict(self):
            return {
                "a": self.a,
                "b": self.b
            }

    assert make_serializable(Obj("hi", 1)) == {"a": "hi", "b": 1}
