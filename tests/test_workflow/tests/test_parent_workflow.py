#! /usr/bin/env python

"""Test hello_world parent workflow"""
import pytest


@pytest.fixture(scope="module")
def project_root_files():
    """
    Override the project root for this test since it doesn't follow a
    standard pattern.
    """
    return ["parent_workflow.wdl"]


@pytest.mark.integration
def test_hello_world_parent_workflow(workflow_data, workflow_runner):
    """Test the hello_world parent workflow with fixed inputs and outputs."""
    inputs = {
        "input_files": [
            workflow_data["test_file"],
            workflow_data["test_file"],
        ]
    }
    expected = {
        "single_file": workflow_data["test_file"]
    }
    workflow_runner(
        "parent_workflow.wdl",
        inputs,
        expected,
        executors=["cromwell"]
    )
