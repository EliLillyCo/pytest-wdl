#! /usr/bin/env python
# -*- coding: utf-8 -*-
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
Convert BAM to SAM for diff.
"""
from pathlib import Path
import re
from typing import Optional

from pytest_wdl.core import DataFile, tempdir


try:
    import pysam
except ImportError:
    raise ImportError(
        "Failed to import dependencies for bam type. To add support for BAM files, "
        "install the plugin with pip install pytest-wdl[bam]"
    )


class BamDataFile(DataFile):
    """
    Supports comparing output of BAM file. This uses pysam to convert BAM to
    SAM, so that DataFile can carry out a regular diff on the SAM files.
    """
    @classmethod
    def _assert_contents_equal(
        cls, file1: Path, file2: Path, allowed_diff_lines: Optional[int] = None
    ):
        cls._diff_contents(file1, file2, allowed_diff_lines)

    @classmethod
    def _diff(cls, file1: Path, file2: Path):
        """
        Special handling for BAM files to read them into SAM so we can
        compare them.

        Args:
            file1:
            file2:
        """
        with tempdir() as temp:
            cmp_file1 = temp / "file1"
            cmp_file2 = temp / "file2"
            _bam_to_sam(file1, cmp_file1)
            _bam_to_sam(file2, cmp_file2)
            return super()._diff(cmp_file1, cmp_file2)


def _bam_to_sam(input_bam: Path, output_sam: Path):
    """Use PySAM to convert bam to sam."""
    samfile = pysam.view("-h", str(input_bam))
    # avoid trailing newline.
    newline = ""
    with open(output_sam, "w") as file_handle:
        for row in samfile.splitlines():
            file_handle.write(newline + _remove_samtools_randomness(row))
            newline = "\n"


def _remove_samtools_randomness(sam_line):
    """Replace the random IDs added by samtools."""
    return re.sub(r"UNSET-\w*\b", "UNSET-placeholder", sam_line)
