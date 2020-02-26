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
from typing import cast

import pytest

from pytest_wdl.core import DefaultDataFile, create_executor
from pytest_wdl.executors import (
    Executor, ExecutionFailedError, InputsFormatter, read_write_inputs
)
from pytest_wdl.utils import tempdir


WORKFLOW_EXECUTORS = ["cromwell", "miniwdl"]
TASK_EXECUTORS = ["miniwdl"]


@pytest.mark.integration
@pytest.mark.parametrize("executor", WORKFLOW_EXECUTORS)
def test_executors(workflow_data, workflow_runner, executor):
    inputs = {
        "in_txt": workflow_data["in_txt"],
        "in_int": 1
    }
    expected = {
        "out_txt": workflow_data["out_txt"],
        "out_int": 1
    }
    workflow_runner(
        "test.wdl",
        inputs,
        expected,
        executors=[executor]
    )
    # Test with the old workflow_runner signature
    workflow_runner(
        "test.wdl",
        "cat_file",
        inputs,
        expected,
        executors=[executor]
    )


@pytest.mark.integration
def test_multiple_executors(workflow_data, workflow_runner):
    inputs = {
        "in_txt": workflow_data["in_txt"],
        "in_int": 1
    }
    expected = {
        "out_txt": workflow_data["out_txt"],
        "out_int": 1
    }

    def callback(executor: str, execution_dir: Path, outputs: dict):
        assert executor in WORKFLOW_EXECUTORS
        assert execution_dir.exists()
        for param in ("cat_file.out_txt", "cat_file.out_int"):
            assert param in outputs

    workflow_runner(
        "test.wdl",
        inputs,
        expected,
        executors=WORKFLOW_EXECUTORS,
        callback=callback
    )


# TODO: figure out how to override default_executors
# def test_workflow_runner_error(workflow_data, workflow_runner):
#     inputs = {
#         "in_txt": workflow_data["in_txt"],
#         "in_int": 1
#     }
#     outputs = {
#         "out_txt": workflow_data["out_txt"],
#         "out_int": 1
#     }
#
#     with pytest.raises(RuntimeError):
#         workflow_runner(
#             "test.wdl",
#             inputs,
#             outputs,
#             executors=[]
#         )


@pytest.mark.integration
@pytest.mark.parametrize("executor", TASK_EXECUTORS)
def test_task(workflow_data, workflow_runner, executor):
    inputs = {
        "in_txt": workflow_data["in_txt"],
    }
    outputs = {
        "out_txt": workflow_data["out_txt"],
    }
    workflow_runner(
        "test.wdl",
        inputs,
        outputs,
        executors=[executor],
        task_name="cat"
    )


@pytest.mark.integration
@pytest.mark.parametrize("executor", WORKFLOW_EXECUTORS)
def test_execution_failure(workflow_data, workflow_runner, executor):
    inputs = {
        "in_txt": workflow_data["in_txt"],
        "in_int": 1,
        "fail": True
    }
    outputs = {
        "out_txt": workflow_data["out_txt"],
        "out_int": 1
    }
    with pytest.raises(ExecutionFailedError) as exc_info:
        workflow_runner(
            "test.wdl",
            inputs,
            outputs,
            executors=[executor]
        )

    err = cast(ExecutionFailedError, exc_info.value)
    assert "foo_fail" in err.failed_task
    assert err.failed_task_exit_status == 1


def test_get_workflow_inputs():
    actual_inputs_dict, inputs_path = read_write_inputs(
        inputs_dict={"bar": 1}, namespace="foo"
    )
    assert inputs_path.exists()
    with open(inputs_path, "rt") as inp:
        assert json.load(inp) == actual_inputs_dict
    assert actual_inputs_dict == {
        "foo.bar": 1
    }

    with tempdir() as d:
        inputs_file = d / "inputs.json"
        actual_inputs_dict, inputs_path = read_write_inputs(
            inputs_dict={"bar": 1}, namespace="foo", inputs_file=inputs_file
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
        actual_inputs_dict, inputs_path = read_write_inputs(
            namespace="foo", inputs_file=inputs_file
        )
        assert inputs_file == inputs_path
        assert inputs_path.exists()
        with open(inputs_path, "rt") as inp:
            assert json.load(inp) == actual_inputs_dict
        assert actual_inputs_dict == inputs_dict


def test_inputs_formatter():
    formatter = InputsFormatter.get_instance()

    assert formatter.format_value(1) == 1
    assert formatter.format_value("foo") == "foo"
    assert formatter.format_value((1.1, 2.2)) == [1.1, 2.2]

    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("foo")
        df = DefaultDataFile(foo)
        assert formatter.format_value(df) == foo
        assert formatter.format_value([df]) == [foo]
        assert formatter.format_value({"a": df}) == {"a": foo}

    class Obj:
        def __init__(self, a: str, b: int):
            self.a = a
            self.b = b

        def as_dict(self):
            return {
                "a": self.a,
                "b": self.b
            }

    assert formatter.format_value(Obj("hi", 1)) == {"a": "hi", "b": 1}


def test_create_executor():
    with pytest.raises(RuntimeError):
        create_executor("foo", [], None)


def test_validate_outputs():
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": 1}, {"bar": 1}, ""
        )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": 1}, {"baz": 1}, "foo"
        )
    Executor._validate_outputs(
        {"foo.bar": None}, {"bar": None}, "foo"
    )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": None}, {"bar": 1}, "foo"
        )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": 1}, {"bar": None}, "foo"
        )
    Executor._validate_outputs(
        {"foo.bar": [1, 2, 3]}, {"bar": [1, 2, 3]}, "foo"
    )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": [1, 2, 3]}, {"bar": [1, 2]}, "foo"
        )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": [1, 2, 3]}, {"bar": [3, 2, 1]}, "foo"
        )
    Executor._validate_outputs(
        {"foo.bar": {"a": 1}}, {"bar": {"a": 1}}, "foo"
    )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": {"a": 1}}, {"bar": {"b": 1}}, "foo"
        )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": {"a": 1}}, {"bar": {"a": 1, "b": 2}}, "foo"
        )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": {"a": 1}}, {"bar": {"a": 2}}, "foo"
        )
    with pytest.raises(AssertionError):
        Executor._validate_outputs(
            {"foo.bar": 1}, {"bar": 2}, "foo"
        )
