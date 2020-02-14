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

from pytest_wdl.data_types.vcf import VcfDataFile
from pytest_wdl.localizers import StringLocalizer
from pytest_wdl.utils import tempdir, find_project_path
from .. import no_internet
import pytest


@pytest.fixture(scope="module")
def workflow_data_descriptor_file(project_root):
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    return find_project_path(
        "tests/test_vcf/test_data.json", start=project_root, assert_exists=True
    )


def test_vcf_data_file_identical():
    with tempdir() as temp:
        localizer1 = StringLocalizer(
            "##fileformat=VCFv4.2\n"
            "chr1\t1111\t.\tA\tG\t1000\tPASS\t.\tGT"
        )
        v1 = VcfDataFile(temp / "foo1.vcf", localizer1)
        localizer2 = StringLocalizer(
            "##fileformat=VCFv4.2\n"
            "chr1\t1111\t.\tA\tG\t999.9\tPASS\t."
        )
        v2 = VcfDataFile(temp / "foo2.vcf", localizer2)
        v1.assert_contents_equal(v2)


def test_vcf_data_file_different():
    with tempdir() as temp:
        localizer1 = StringLocalizer(
            "##fileformat=VCFv4.2\n"
            "chr1\t1111\t.\tA\tG\t1000\tPASS\t."
        )
        v1 = VcfDataFile(temp / "foo1.vcf", localizer1, allowed_diff_lines=0)
        localizer2 = StringLocalizer(
            "##fileformat=VCFv4.2\n"
            "chr1\t1111\t.\tA\tG\t999.9\tPASS\t.\n"
            "chr1\t2222\t.\tT\tC\t500\tPASS\t."
        )
        v2 = VcfDataFile(temp / "foo2.vcf", localizer2)
        with pytest.raises(AssertionError):
            v1.assert_contents_equal(v2)
        v1.set_compare_opts(allowed_diff_lines=1)
        v1.assert_contents_equal(v2)


@pytest.mark.skipif(no_internet, reason="no internet available")
@pytest.mark.integration
def test_vcf(workflow_data, workflow_runner):
    workflow_runner(
        wdl_script="tests/test_vcf/test_vcf.wdl",
        workflow_name="test_vcf",
        inputs=workflow_data.get_dict("vcf"),
        expected=workflow_data.get_dict("output_vcf"),
        executors=["cromwell"]
    )
