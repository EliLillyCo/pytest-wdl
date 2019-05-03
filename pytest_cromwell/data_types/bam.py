#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Convert BAM to SAM for diff.
"""
import os

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
    bamfile = pysam.AlignmentFile(input_bam, 'rb')
    samfile = pysam.AlignmentFile(output_sam, 'w', template=bamfile)
    for read in bamfile:
        samfile.write(read)
