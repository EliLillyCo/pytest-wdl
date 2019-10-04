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
from functools import partial
from pathlib import Path
import re

import subby

from pytest_wdl.data_types import DataFile, assert_text_files_equal, diff_default
from pytest_wdl.utils import tempdir


GENO_RE = re.compile("[|/]")


class VcfDataFile(DataFile):
    def _assert_contents_equal(self, other_path: Path, other_opts: dict) -> None:
        compare_phase = (
            self.compare_opts.get("compare_phase") or
            other_opts.get("compare_phase")
        )
        try:
            assert_text_files_equal(
                self.path,
                other_path,
                self._get_allowed_diff_lines(other_opts),
                diff_fn=partial(diff_vcf_columns, compare_phase=compare_phase)
            )
        except AssertionError as err:
            raise AssertionError(
                f"VCF files are not equal: {self.path} != {other_path}"
            ) from err


def diff_vcf_columns(file1: Path, file2: Path, compare_phase: bool = False) -> int:
    with tempdir() as temp:
        def make_comparable(infile, outfile):
            cmd = ["grep -vE '^#'", "cut -f 1-5,7,10", "cut -d ':' -f 1"]
            output = subby.sub(cmd, stdin=infile)
            with open(outfile, "wt") as out:
                if compare_phase:
                    out.write(output)
                else:
                    # Normalize the allele separator and sort the alleles
                    for row in output.splitlines(keepends=True):
                        r, g = row.rsplit("\t", 1)
                        g_strip = g.rstrip()
                        g_norm = "/".join(sorted(GENO_RE.split(g_strip)))
                        out.write(f"{r}\t{g_norm}")
                        if len(g) != len(g_strip):
                            out.write("\n")

        cmp_file1 = temp / "file1"
        cmp_file2 = temp / "file2"
        make_comparable(file1, cmp_file1)
        make_comparable(file2, cmp_file2)
        return diff_default(cmp_file1, cmp_file2)
