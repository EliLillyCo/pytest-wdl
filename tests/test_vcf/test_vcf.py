from pytest_cromwell.data_types.vcf import VcfDataFile
from pytest_cromwell.core import StringLocalizer
from pytest_cromwell.utils import tempdir, find_project_path
from .. import no_internet
import pytest


@pytest.fixture(scope="module")
def test_data_file(project_root):
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    return find_project_path(
        "tests/test_vcf/test_data.json", start=project_root, assert_exists=True
    )


def test_vcf_data_file_identical():
    with tempdir() as temp:
        localizer1 = StringLocalizer(
            "chr1\t1111\t.\tA\tG\t1000\tPASS\t.\tGT"
        )
        v1 = VcfDataFile(temp / "foo1.vcf", localizer1)
        localizer2 = StringLocalizer(
            "chr1\t1111\t.\tA\tG\t999.9\tPASS\t."
        )
        v2 = VcfDataFile(temp / "foo2.vcf", localizer2)
        v1.assert_contents_equal(v2)


def test_vcf_data_file_different():
    with tempdir() as temp:
        localizer1 = StringLocalizer(
            "chr1\t1111\t.\tA\tG\t1000\tPASS\t.\n"
        )
        v1 = VcfDataFile(temp / "foo1.vcf", localizer1, allowed_diff_lines=1)
        localizer2 = StringLocalizer(
            "chr1\t1111\t.\tA\tG\t999.9\tPASS\t.\n"
            "chr1\t2222\t.\tT\tC\t500\tPASS\t.\n"
        )
        v2 = VcfDataFile(temp / "foo2.vcf", localizer2)
        v1.assert_contents_equal(v2)


@pytest.mark.skipif(no_internet, reason="no internet available")
def test_vcf(test_data, workflow_runner):
    workflow_runner(
        wdl_script="tests/test_vcf/test_vcf.wdl",
        workflow_name="test_vcf",
        inputs={"vcf": test_data["vcf"]},
        expected={"output_vcf": test_data["output_vcf"]}
    )
