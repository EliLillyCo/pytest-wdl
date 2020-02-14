#! /usr/bin/env python

"""Test hello_world task"""
import pytest


@pytest.fixture(scope="module")
def project_root_files():
    """
    Override the project root for this test since it doesn't follow a
    standard pattern.
    """
    return ["parent_workflow.wdl"]


@pytest.mark.integration
def test_hello_world(workflow_data, workflow_runner):
    """Test the hello_world task with fixed inputs and outputs."""
    inputs = {
        "input_file": workflow_data["test_file"],
        "output_filename": "pytest_wdl_readme.md"
    }
    expected = {
        "output_file": workflow_data["test_file"]
    }
    workflow_runner(
        "test_hello_world.wdl",
        inputs=inputs,
        expected=expected,
        executors=["cromwell"]
    )
