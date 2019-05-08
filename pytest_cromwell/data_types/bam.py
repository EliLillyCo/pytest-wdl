#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Convert BAM to SAM for diff.
"""
import os
import re

from pytest_cromwell.core import DataFile, tempdir


try:
    import pysam
except ImportError:
    raise ImportError(
        "Failed to import dependencies for bam type. To add support for BAM files, "
        "install the plugin with pip install pytest-cromwell[bam]"
    )


class BamDataFile(DataFile):
    """
    Supports comparing output of BAM file. This uses pysam to convert BAM to
    SAM, so that DataFile can carry out a regular diff on the SAM files.
    """
    @classmethod
    def _assert_contents_equal(cls, file1, file2, allowed_diff_lines):
        cls._diff_contents(file1, file2, allowed_diff_lines)

    @classmethod
    def _diff(cls, file1, file2):
        """
        Special handling for BAM files to read them into SAM so we can
        compare them.

        Args:
            file1:
            file2:
        """
        with tempdir() as temp:
            cmp_file1 = os.path.join(temp, "file1")
            cmp_file2 = os.path.join(temp, "file2")
            _bam_to_sam(file1, cmp_file1)
            _bam_to_sam(file2, cmp_file2)
            return super()._diff(cmp_file1, cmp_file2)


def _bam_to_sam(input_bam, output_sam):
    """Use PySAM to convert bam to sam."""
    samfile = pysam.view('-h', input_bam)
    # avoid trailing newline.
    newline = ''
    with open(output_sam, 'w') as file_handle:
        for row in samfile.splitlines():
            file_handle.write(newline + _remove_samtools_randomness(row))
            newline = '\n'


def _remove_samtools_randomness(sam_line):
    """Replace the random IDs added by samtools."""
    return re.sub(r'UNSET-\w*\b', 'UNSET-placeholder', sam_line)
