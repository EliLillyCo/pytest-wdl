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
from typing import cast

import pytest

from pytest_wdl.core import EXECUTORS, DefaultDataFile, create_executor
from pytest_wdl.executors import (
    ExecutionFailedError, get_workflow_inputs, make_serializable, validate_outputs
)
from pytest_wdl.utils import tempdir


@pytest.mark.integration
@pytest.mark.parametrize("executor", EXECUTORS.keys())
def test_executors(workflow_data, workflow_runner, executor):
    inputs = {
        "in_txt": workflow_data["in_txt"],
        "in_int": 1
    }
    outputs = {
        "out_txt": workflow_data["out_txt"],
        "out_int": 1
    }
    workflow_runner(
        "test.wdl",
        inputs,
        outputs,
        executors=[executor]
    )
    # Test with the old workflow_runner signature
    workflow_runner(
        "test.wdl",
        "cat_file",
        inputs,
        outputs,
        executors=[executor]
    )


@pytest.mark.integration
def test_multiple_executors(workflow_data, workflow_runner):
    inputs = {
        "in_txt": workflow_data["in_txt"],
        "in_int": 1
    }
    outputs = {
        "out_txt": workflow_data["out_txt"],
        "out_int": 1
    }
    workflow_runner(
        "test.wdl",
        inputs,
        outputs,
        executors=EXECUTORS.keys()
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
@pytest.mark.parametrize("executor", ["miniwdl"])
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
@pytest.mark.parametrize("executor", EXECUTORS.keys())
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


def test_make_serializable():
    assert make_serializable(1) == 1
    assert make_serializable("foo") == "foo"
    assert make_serializable((1.1, 2.2)) == [1.1, 2.2]

    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("foo")
        df = DefaultDataFile(foo)
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


def test_create_executor():
    with pytest.raises(RuntimeError):
        create_executor("foo", [], None)


def test_validate_outputs():
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": 1}, {"bar": 1}, ""
        )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": 1}, {"baz": 1}, "foo"
        )
    validate_outputs(
        {"foo.bar": None}, {"bar": None}, "foo"
    )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": None}, {"bar": 1}, "foo"
        )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": 1}, {"bar": None}, "foo"
        )
    validate_outputs(
        {"foo.bar": [1, 2, 3]}, {"bar": [1, 2, 3]}, "foo"
    )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": [1, 2, 3]}, {"bar": [1, 2]}, "foo"
        )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": [1, 2, 3]}, {"bar": [3, 2, 1]}, "foo"
        )
    validate_outputs(
        {"foo.bar": {"a": 1}}, {"bar": {"a": 1}}, "foo"
    )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": {"a": 1}}, {"bar": {"b": 1}}, "foo"
        )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": {"a": 1}}, {"bar": {"a": 1, "b": 2}}, "foo"
        )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": {"a": 1}}, {"bar": {"a": 2}}, "foo"
        )
    with pytest.raises(AssertionError):
        validate_outputs(
            {"foo.bar": 1}, {"bar": 2}, "foo"
        )
