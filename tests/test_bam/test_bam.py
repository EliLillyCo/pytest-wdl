#! /usr/bin/env python
#
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

"""
Test that bam data_type works.
"""
from typing import cast

from .. import no_internet
import pytest

from pytest_wdl.data_types.bam import BamDataFile
from pytest_wdl.utils import find_project_path


@pytest.fixture(scope="module")
def workflow_data_descriptor_file(project_root):
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    return find_project_path(
        "tests/test_bam/test_data.json", start=project_root, assert_exists=True
    )


@pytest.mark.skipif(no_internet, reason="no internet available")
@pytest.mark.integration
def test_bam(workflow_data, workflow_runner):
    workflow_runner(
        wdl_script="tests/test_bam/test_bam.wdl",
        workflow_name="test_bam",
        inputs={"bam": workflow_data["bam"]},
        expected={"output_bam": workflow_data["output_bam"]},
        executors=["cromwell"]
    )


def test_bam_removing_randomness(workflow_data):
    """Test that BAMs with the only difference being random IDs
    added by samtools are evaluated as equal."""
    b1 = workflow_data["random_id_bam_input"]
    b2 = workflow_data["random_id_bam_output"]
    cast(BamDataFile, b2).assert_contents_equal(b1)


def test_bam_diff(workflow_data):
    b1 = workflow_data["random_id_bam_output"]
    b2 = workflow_data["ignorable_difference"]
    cast(BamDataFile, b1).assert_contents_equal(b2)

    b3 = workflow_data["non_ignorable_difference"]
    with pytest.raises(AssertionError):
        cast(BamDataFile, b1).assert_contents_equal(b3)

    cast(BamDataFile, b3).compare_opts["allowed_diff_lines"] = 1
    cast(BamDataFile, b1).assert_contents_equal(b3)
