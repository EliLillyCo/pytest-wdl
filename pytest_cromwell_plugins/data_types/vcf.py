#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
Remove columns in a VCF after qual line so comparisons can be made. Some tools
that generate VCF (callers) will result in very slightly different qual scores
when run on different hardware.
"""

import os

import delegator

from pytest_cromwell_core.utils import DataFile, tempdir


class VcfDataFile(DataFile):
    name = "vcf"

    @classmethod
    def _assert_contents_equal(cls, file1, file2, allowed_diff_lines):
        cls._diff_contents(file1, file2, allowed_diff_lines)

    @classmethod
    def _diff(cls, file1, file2):
        """
        Special handling for VCF files to only compare the first 5 columns.

        Args:
            file1:
            file2:
        """
        with tempdir() as temp:
            cmp_file1 = os.path.join(temp, "file1")
            cmp_file2 = os.path.join(temp, "file2")
            job1 = delegator.run(
                f"cat {file1} | grep -vP '^#' | cut -d$'\t' -f 1-5 > {cmp_file1}"
            )
            job2 = delegator.run(
                f"cat {file2} | grep -vP '^#' | cut -d$'\t' -f 1-5 > {cmp_file2}"
            )
            for job in (job1, job2):
                job.block()
            return super()._diff(cmp_file1, cmp_file2)
