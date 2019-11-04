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
from functools import partial
from pathlib import Path
import re
from typing import Iterable, Optional

import subby

from pytest_wdl.data_types import DataFile, assert_text_files_equal, diff_default
from pytest_wdl.utils import tempdir

# TODO: fall back to command line samtools (if installed)
import pysam


INVARIATE_COLUMNS = "1,2,5,10,11"
ALL_COLUMNS = "1-11"


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
        try:
            assert_bam_files_equal(
                self.path,
                other_path,
                allowed_diff_lines=self._get_allowed_diff_lines(other_opts),
                min_mapq=self._get_min_mapq(other_opts),
                compare_tag_columns=self._get_compare_tag_columns(other_opts)
            )
        except AssertionError as err:
            raise AssertionError(
                f"BAM files are not equal: {self.path} != {other_path}"
            ) from err

    def _get_min_mapq(self, other_opts: dict) -> int:
        return max(
            self.compare_opts.get("min_mapq", 0),
            other_opts.get("min_mapq", 0)
        )

    def _get_compare_tag_columns(self, other_opts: dict) -> bool:
        return (
            self.compare_opts.get("compare_tag_columns") or
            other_opts.get("compare_tag_columns")
        )


def assert_bam_files_equal(
    file1: Path,
    file2: Path,
    allowed_diff_lines: int = 0,
    min_mapq: int = 0,
    compare_tag_columns: bool = False
):
    """
    Compare two BAM files:
    * Convert them to SAM format
    * Optionally re-sort the files by chromosome, position, and flag
    * First compare all lines using only a subset of columns that should be
    deterministic
    * Next, filter the files by MAPQ and compare the remaining rows using all columns

    Args:
        file1: First BAM to compare
        file2: Second BAM to compare
        allowed_diff_lines: Number of lines by which the BAMs are allowed to differ
            (after being convert to SAM)
        min_mapq: Minimum mapq used to filter reads when comparing all columns
        compare_tag_columns: Whether to include tag columns (12+) when comparing
            all columns
    """
    with tempdir() as temp:
        # Compare all reads using subset of columns
        cmp_file1 = temp / "all_reads_subset_columns_file1"
        cmp_file2 = temp / "all_reads_subset_columns_file2"
        bam_to_sam(
            file1,
            cmp_file1,
            headers=None,
            sorting=Sorting.NAME
        )
        bam_to_sam(
            file2,
            cmp_file2,
            headers=None,
            sorting=Sorting.NAME
        )
        assert_text_files_equal(
            cmp_file1,
            cmp_file2,
            allowed_diff_lines,
            diff_fn=partial(diff_bam_columns, columns=INVARIATE_COLUMNS)
        )

        # Compare subset of reads using all columns
        cmp_file1 = temp / "subset_reads_all_columns_file1"
        cmp_file2 = temp / "subset_reads_all_columns_file2"
        bam_to_sam(
            file1,
            cmp_file1,
            min_mapq=min_mapq,
            sorting=Sorting.COORDINATE,
        )
        bam_to_sam(
            file2,
            cmp_file2,
            min_mapq=min_mapq,
            sorting=Sorting.COORDINATE
        )
        if compare_tag_columns:
            diff_fn = diff_default
        else:
            diff_fn = partial(diff_bam_columns, columns=ALL_COLUMNS)
        assert_text_files_equal(
            cmp_file1,
            cmp_file2,
            allowed_diff_lines,
            diff_fn=diff_fn
        )


def bam_to_sam(
    input_bam: Path,
    output_sam: Path,
    headers: Optional[Iterable[str]] = ("HD", "SQ", "RG"),
    min_mapq: Optional[int] = None,
    sorting: Sorting = Sorting.NONE
):
    """
    Use PySAM to convert bam to sam.
    """
    opts = []
    if headers:
        opts.append("-h")
        headers = set(headers)
    if min_mapq:
        opts.extend(["-q", str(min_mapq)])
    sam = pysam.view(*opts, str(input_bam)).rstrip()
    # Replace any randomly assigned readgroups with a common placeholder
    sam = re.sub(r"UNSET-\w*\b", "UNSET-placeholder", sam)

    lines = sam.splitlines(keepends=True)
    header_lines = []
    start = 0
    if headers:
        for i, line in enumerate(lines):
            if not line.startswith("@"):
                start = i
                break
            elif line[1:3] in headers:
                header_lines.append(line)

    body_lines = lines[start:]
    if sorting is not Sorting.NONE:
        with tempdir() as temp:
            temp_sam = temp / f"output_{str(output_sam.stem)}.sam"
            with open(temp_sam, "w") as out:
                out.write("".join(body_lines))
            if sorting is Sorting.COORDINATE:
                sort_cols = "-k3,3 -k4,4n -k2,2n"
            else:
                sort_cols = "-k1,1 -k2,2n"
            sorted_sam = subby.sub(f"cat {str(temp_sam)} | sort {sort_cols}")
            body_lines = [sorted_sam]

    with open(output_sam, "w") as out:
        out.write("".join(header_lines + body_lines))


def diff_bam_columns(file1: Path, file2: Path, columns: str) -> int:
    with tempdir() as temp:
        def make_comparable(inpath, output):
            subby.run(f"cat {inpath} | cut -f {columns}", stdout=output)

        cmp_file1 = temp / "cmp_file1"
        cmp_file2 = temp / "cmp_file2"
        make_comparable(file1, cmp_file1)
        make_comparable(file2, cmp_file2)
        return diff_default(cmp_file1, cmp_file2)
