#! /usr/bin/env python

"""
Test that bam data_type works.
"""
from pytest_wdl.utils import find_project_path
from .. import no_internet
import pytest


@pytest.fixture(scope="module")
def test_data_file(project_root):
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    return find_project_path(
        "tests/test_bam/test_data.json", start=project_root, assert_exists=True
    )


@pytest.mark.skipif(no_internet, reason="no internet available")
def test_bam(test_data, workflow_runner):
    workflow_runner(
        wdl_script='tests/test_bam/test_bam.wdl',
        workflow_name='test_bam',
        inputs={"bam": test_data["bam"]},
        expected={"output_bam": test_data["output_bam"]}
    )


def test_bam_removing_randomness(test_data, workflow_runner):
    """Test that BAMs with the only difference being random IDs
    added by samtools are evaluated as equal."""
    workflow_runner(
        wdl_script='tests/test_bam/test_bam_norandom.wdl',
        workflow_name='test_bam_no_random',
        inputs={
            "bam": test_data["random_id_bam_input"]
        },
        expected={
            "output_bam": test_data["random_id_bam_output"]
        }
    )
