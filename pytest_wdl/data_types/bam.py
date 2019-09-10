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
Convert BAM to SAM for diff.
"""
from enum import Enum
from pathlib import Path
import re
from typing import Optional

import subby

from pytest_wdl.data_types import DataFile, assert_text_files_equal, diff_default
from pytest_wdl.utils import tempdir

try:  # pragma: no-cover
    import pysam
except ImportError:
    raise ImportError(
        "Failed to import dependencies for bam type. To add support for BAM files, "
        "install the plugin with pip install pytest-wdl[bam]"
    )


class Sorting(Enum):
    NONE = 0
    COORDINATE = 1
    NAME = 2


class BamDataFile(DataFile):
    """
    Supports comparing output of BAM file. This uses pysam to convert BAM to
    SAM, so that DataFile can carry out a regular diff on the SAM files.
    """
    def _assert_contents_equal(self, other_path: Path, other_opts: dict):
        assert_bam_files_equal(
            self.path,
            other_path,
            allowed_diff_lines=self._get_allowed_diff_lines(other_opts),
            min_mapq=self._get_min_mapq(other_opts)
        )

    def _get_min_mapq(self, other_opts: dict) -> int:
        return max(
            self.compare_opts.get("min_mapq", 0),
            other_opts.get("min_mapq", 0)
        )


def assert_bam_files_equal(
    file1: Path,
    file2: Path,
    allowed_diff_lines: int = 0,
    min_mapq: int = 0,
    assume_sorted: bool = False
):
    """
    Compare two BAM files:
    * Convert them to SAM format
    * Optionally re-sort the files by chromosome, position, and flag
    * First compare all lines using only a subset of columns that should be
    deterministic
    * Next, filter the files by MAPQ and compare the remaining rows using all columns

    Args:
        file1:
        file2:
        allowed_diff_lines:
        min_mapq:
        assume_sorted:
    """
    with tempdir() as temp:
        # Compare all reads using subset of columns
        cmp_file1 = temp / "all_reads_subset_columns_file1"
        cmp_file2 = temp / "all_reads_subset_columns_file2"
        bam_to_sam(
            file1,
            cmp_file1,
            headers=False,
            sorting=Sorting.NONE if assume_sorted else Sorting.NAME
        )
        bam_to_sam(
            file2,
            cmp_file2,
            headers=False,
            sorting=Sorting.NONE if assume_sorted else Sorting.NAME
        )
        assert_text_files_equal(
            cmp_file1, cmp_file2, allowed_diff_lines, diff_bam_columns
        )

        # Compare subset of reads using all columns
        cmp_file1 = temp / "subset_reads_all_columns_file1"
        cmp_file2 = temp / "subset_reads_all_columns_file2"
        bam_to_sam(
            file1,
            cmp_file1,
            headers=True,
            min_mapq=min_mapq,
            sorting=Sorting.NONE if assume_sorted else Sorting.COORDINATE
        )
        bam_to_sam(
            file2,
            cmp_file2,
            headers=True,
            min_mapq=min_mapq,
            sorting=Sorting.NONE if assume_sorted else Sorting.COORDINATE
        )
        assert_text_files_equal(cmp_file1, cmp_file2, allowed_diff_lines)


def bam_to_sam(
    input_bam: Path,
    output_sam: Path,
    headers: bool = True,
    min_mapq: Optional[int] = None,
    sorting: Sorting = Sorting.NONE
):
    """
    Use PySAM to convert bam to sam.
    """
    opts = []
    if headers:
        opts.append("-h")
    if min_mapq:
        opts.extend(["-q", str(min_mapq)])
    sam = pysam.view(*opts, str(input_bam)).rstrip()
    # Replace any randomly assigned readgroups with a common placeholder
    sam = re.sub(r"UNSET-\w*\b", "UNSET-placeholder", sam)

    if sorting is not Sorting.NONE:
        lines = sam.splitlines(keepends=True)
        start = 0
        if headers:
            for i, line in enumerate(lines):
                if not line.startswith("@"):
                    start = i
                    break

        with tempdir() as temp:
            temp_sam = temp / f"output_{str(output_sam.stem)}.sam"
            with open(temp_sam, "w") as out:
                out.write("".join(lines[start:]))
            if sorting is Sorting.COORDINATE:
                sort_cols = "-k3,3 -k4,4n -k2,2n"
            else:
                sort_cols = "-k1,1 -k2,2n"
            c = subby.run(
                f"cat {str(temp_sam)} | sort -t'\t' {sort_cols}"
            )
            lines = lines[:start] + [c.output.decode()]

    with open(output_sam, "w") as out:
        out.write("".join(lines))


def diff_bam_columns(file1: Path, file2: Path) -> int:
    with tempdir() as temp:
        def make_comparable(inpath, output):
            job = subby.run(f"cat {inpath} | cut -f 1,2,5,10,11")
            with open(output, "wb") as out:
                out.write(job.output)

        cmp_file1 = temp / "cmp_file1"
        cmp_file2 = temp / "cmp_file2"
        make_comparable(file1, cmp_file1)
        make_comparable(file2, cmp_file2)
        return diff_default(cmp_file1, cmp_file2)
