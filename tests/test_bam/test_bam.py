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
    return os.path.join(project_root, "tests/test_bam/test_data.json")


def test_bam(test_data, workflow_runner):
    workflow_runner(
        wdl_script='tests/test_bam/test_bam.wdl',
        workflow_name='test_bam',
        inputs={"bam": test_data["bam"]},
        expected={"output_bam": test_data["output_bam"]}
    )


from pytest_cromwell import DataFile


class DataDirNgWrapper:
    def __init__(self, datadir):
        self.datadir = datadir

    def __getitem__(self, name):
        return DataFile(path=self.datadir[name])


@pytest.fixture(scope="function")
def datadir_wrapper(datadir):
    """
    Provides an interface to pytest-datadir-ng that is compatible with
    `cromwell_harness`.

    Args:
        datadir: datadir fixture.

    Returns:
        DataFile objects.
    """
    return DataDirNgWrapper(datadir)


def test_bam_removing_randomness(test_data_ng, workflow_runner):
    """Test that BAMs with the only difference being random IDs
    added by samtools are evaluated as equal."""
    workflow_runner(
        wdl_script='tests/test_bam/test_bam_norandom.wdl',
        workflow_name='test_bam_no_random',
        inputs={
            "bam": test_data_ng["samtools_random_ids_UNSET-4F784850.bam"]
        },
        expected={
            "output_bam": test_data_ng["samtools_random_ids_UNSET-different.bam"]
        }
    )
