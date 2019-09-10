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
from abc import ABCMeta, abstractmethod
import hashlib
from pathlib import Path
from typing import Callable, Optional, Union, cast

import subby

from pytest_wdl.localizers import Localizer
from pytest_wdl.utils import tempdir


class DataFile(metaclass=ABCMeta):
    """
    A data file, which may be local, remote, or represented as a string.

    Args:
        local_path: Path where the data file should exist after being localized.
        localizer: Localizer object, for persisting the file on the local disk.
        allowed_diff_lines: Number of lines by which the file is allowed to differ
            from another and still be considered equal.
        compare_opts: Additional type-specific comparison options.
    """
    def __init__(
        self,
        local_path: Path,
        localizer: Optional[Localizer] = None,
        **compare_opts
    ):
        if localizer is None and not local_path.exists():
            raise ValueError(
                f"Local path {local_path} does not exist and 'localizer' is None"
            )
        self.local_path = local_path
        self.localizer = localizer
        self.compare_opts = compare_opts

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
        other_compare_opts = {}
        if isinstance(other, Path):
            other_path = other
        elif isinstance(other, str):
            other_path = Path(other)
        else:
            other_df = cast(DataFile, other)
            other_path = other_df.path
            other_compare_opts = other.compare_opts

        self._assert_contents_equal(other_path, other_compare_opts)

    @abstractmethod
    def _assert_contents_equal(self, other_path: Path, other_opts: dict) -> None:
        pass

    def _get_allowed_diff_lines(self, other_opts: dict):
        return max(
            self.compare_opts.get("allowed_diff_lines", 0),
            other_opts.get("allowed_diff_lines", 0)
        )


class DefaultDataFile(DataFile):
    def _assert_contents_equal(self, other_path: Path, other_opts: dict):
        allowed_diff_lines = self._get_allowed_diff_lines(other_opts)
        if allowed_diff_lines:
            assert_text_files_equal(self.path, other_path, allowed_diff_lines)
        else:
            assert_hashes_equal(self.path, other_path)


def diff_default(file1: Path, file2: Path) -> int:
    cmds = [
        f"diff -y --suppress-common-lines --ignore-trailing-space {file1} {file2}",
        "grep -c '^'"
    ]
    # It's a valid result to have no lines match, so allow a grep returncode of 1
    return int(subby.run(cmds, allowed_return_codes=(0, 1)).output)


def assert_text_files_equal(
    file1: Path,
    file2: Path,
    allowed_diff_lines: int = 0,
    diff_fn: Callable[[Path, Path], int] = diff_default
) -> None:
    if file1.suffix == ".gz":
        with tempdir() as temp:
            temp_file1 = temp / "file1"
            temp_file2 = temp / "file2"
            subby.run(f"gunzip -c {file1}", stdout=temp_file1)
            subby.run(f"gunzip -c {file2}", stdout=temp_file2)
            diff_lines = diff_fn(temp_file1, temp_file2)
    else:
        diff_lines = diff_fn(file1, file2)

    if diff_lines > allowed_diff_lines:
        raise AssertionError(
            f"{diff_lines} lines (which is > {allowed_diff_lines} allowed) are "
            f"different between files {file1}, {file2}"
        )


def assert_hashes_equal(
    file1: Path,
    file2: Path,
    hash_fn: Callable[[bytes], hashlib._hashlib.HASH] = hashlib.md5
) -> None:
    with open(file1, "rb") as inp1:
        file1_md5 = hash_fn(inp1.read()).hexdigest()
    with open(file2, "rb") as inp2:
        file2_md5 = hash_fn(inp2.read()).hexdigest()
    if file1_md5 != file2_md5:
        raise AssertionError(
            f"MD5 hashes differ between expected identical files "
            f"{file1}, {file2}"
        )
