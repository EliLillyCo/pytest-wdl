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
import hashlib
from pathlib import Path
from typing import Optional, Union

import delegator

from pytest_wdl.localizers import Localizer
from pytest_wdl.utils import tempdir


class DataFile:
    """
    A data file, which may be local, remote, or represented as a string.

    Args:
        local_path: Path where the data file should exist after being localized.
        localizer: Localizer object, for persisting the file on the local disk.
        allowed_diff_lines: Number of lines by which the file is allowed to differ
            from another and still be considered equal.
    """
    def __init__(
        self,
        local_path: Path,
        localizer: Optional[Localizer] = None,
        allowed_diff_lines: Optional[int] = 0
    ):
        if localizer is None and not local_path.exists():
            raise ValueError(
                f"Local path {local_path} does not exist and 'localizer' is None"
            )
        self.local_path = local_path
        self.localizer = localizer
        self.allowed_diff_lines = allowed_diff_lines or 0

    @property
    def path(self) -> Path:
        if not self.local_path.exists():
            self.localizer.localize(self.local_path)
        return self.local_path

    def __str__(self) -> str:
        return str(self.local_path)

    def assert_contents_equal(self, other: Union[str, Path, "DataFile"]) -> None:
        """
        Assert the contents of two files are equal.

        If `allowed_diff_lines == 0`, files are compared using MD5 hashes, otherwise
        their contents are compared using the linux `diff` command.

        Args:
            other: A `DataFile` or string file path.

        Raises:
            AssertionError if the files are different.
        """
        allowed_diff_lines = self.allowed_diff_lines

        if isinstance(other, Path):
            other_path = other
        elif isinstance(other, str):
            other_path = Path(other)
        else:
            other_path = other.path
            allowed_diff_lines = max(allowed_diff_lines, other.allowed_diff_lines)

        self._assert_contents_equal(self.path, other_path, allowed_diff_lines)

    @classmethod
    def _assert_contents_equal(
        cls, file1: Path, file2: Path, allowed_diff_lines: int
    ) -> None:
        if allowed_diff_lines:
            cls._diff_contents(file1, file2, allowed_diff_lines)
        else:
            cls._compare_hashes(file1, file2)

    @classmethod
    def _diff_contents(cls, file1: Path, file2: Path, allowed_diff_lines: int) -> None:
        if file1.suffix == ".gz":
            with tempdir() as temp:
                temp_file1 = temp / "file1"
                temp_file2 = temp / "file2"
                delegator.run(f"gunzip -c {file1} > {temp_file1}", block=True)
                delegator.run(f"gunzip -c {file2} > {temp_file2}", block=True)
                diff_lines = cls._diff(temp_file1, temp_file2)
        else:
            diff_lines = cls._diff(file1, file2)

        if diff_lines > allowed_diff_lines:
            raise AssertionError(
                f"{diff_lines} lines (which is > {allowed_diff_lines} allowed) are "
                f"different between files {file1}, {file2}"
            )

    @classmethod
    def _diff(cls, file1: Path, file2: Path) -> int:
        cmd = f"diff -y --suppress-common-lines {file1} {file2} | grep '^' | wc -l"
        return int(delegator.run(cmd, block=True).out)

    @classmethod
    def _compare_hashes(cls, file1: Path, file2: Path) -> None:
        with open(file1, "rb") as inp1:
            file1_md5 = hashlib.md5(inp1.read()).hexdigest()
        with open(file2, "rb") as inp2:
            file2_md5 = hashlib.md5(inp2.read()).hexdigest()
        if file1_md5 != file2_md5:
            raise AssertionError(
                f"MD5 hashes differ between expected identical files "
                f"{file1}, {file2}"
            )
