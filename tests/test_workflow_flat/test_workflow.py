#! /usr/bin/env python

"""Test hello_world parent workflow"""
import pytest


@pytest.mark.integration
def test_workflow(workflow_data, workflow_runner):
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
        "workflow.wdl",
        inputs,
        expected,
        executors=["cromwell"]
    )
