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
Some tools that generate VCF (callers) will result in very slightly different qual
scores and other floating-point-valued fields when run on different hardware. This
handler ignores the QUAL and INFO columns and only compares the genotype (GT) field
of sample columns. Only works for single-sample VCFs.
"""
from pathlib import Path
from typing import Optional

import delegator

from pytest_wdl.core import DataFile
from pytest_wdl.utils import tempdir


class VcfDataFile(DataFile):
    @classmethod
    def _assert_contents_equal(
        cls, file1: Path, file2: Path, allowed_diff_lines: Optional[int] = None
    ):
        cls._diff_contents(file1, file2, allowed_diff_lines)

    @classmethod
    def _diff(cls, file1: Path, file2: Path):
        """
        Special handling for VCF files to ignore QUAL, INFO, and FORMAT, and only
        compares genotypes in the first sample column

        Args:
            file1: First file to compare
            file2: Second file to compare
        """
        with tempdir() as temp:
            cmp_file1 = temp / "file1"
            cmp_file2 = temp / "file2"
            job1 = delegator.run(
                f"cat {file1} | grep -vP '^#' | cut -d$'\t' -f 1-5,7,10 | cut -d$':' -f 1 > {cmp_file1}"
            )
            job2 = delegator.run(
                f"cat {file2} | grep -vP '^#' | cut -d$'\t' -f 1-5,7,10 | cut -d$':' -f 1 > {cmp_file2}"
            )
            for job in (job1, job2):
                job.block()
            return super()._diff(cmp_file1, cmp_file2)
