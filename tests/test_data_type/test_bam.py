#! /usr/bin/env python

"""
Test that bam data_type works.
"""
import os

import pytest


@pytest.fixture(scope="module")
def test_data_file(project_root):
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    return os.path.join(project_root, "tests/test_data_type/test_data.json")


def test_bam(test_data, workflow_runner):
    workflow_runner(
        wdl_script='tests/test_data_type/test_bam.wdl',
        workflow_name='test_bam',
        inputs={"bam": test_data["bam"]},
        expected={"output_bam": test_data["output_bam"]}
    )
