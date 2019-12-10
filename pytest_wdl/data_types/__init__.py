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
from pathlib import Path
from typing import Callable, Optional, Union, cast

import subby

from pytest_wdl.localizers import Localizer
from pytest_wdl.utils import compare_files_with_hash, ensure_path, tempdir
from xphyle import guess_file_format
from xphyle.utils import transcode_file

DEFAULT_TYPE = "default"
ALLOWED_DIFF_LINES = "allowed_diff_lines"


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
            if self.localizer:
                ensure_path(self.local_path, is_file=True, create=True)
                self.localizer.localize(self.local_path)
            else:
                raise RuntimeError(
                    f"Localization to {self.local_path} is required but no localizer "
                    f"is defined"
                )
        return self.local_path

    def __str__(self) -> str:
        return str(self.local_path)

    def set_compare_opts(self, **kwargs):
        """
        Update comparison options.

        Args:
            **kwargs: Comparison options to update.
        """
        self.compare_opts.update(kwargs)

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
            self.compare_opts.get(ALLOWED_DIFF_LINES, 0),
            other_opts.get(ALLOWED_DIFF_LINES, 0)
        )


class DefaultDataFile(DataFile):
    def _assert_contents_equal(self, other_path: Path, other_opts: dict):
        allowed_diff_lines = self._get_allowed_diff_lines(other_opts)
        if allowed_diff_lines:
            assert_text_files_equal(self.path, other_path, allowed_diff_lines)
        else:
            assert_binary_files_equal(self.path, other_path)


def diff_default(file1: Path, file2: Path) -> int:
    """
    Default diff command.

    Args:
        file1: First file to compare
        file2: Second file to compare

    Returns:
        Number of different lines.
    """
    with tempdir() as temp:
        # Remove trailing whitespace, and ensure a newline at the end of the file
        cmp_file1 = temp / "file1"
        cmp_file2 = temp / "file2"
        subby.run("sed 's/[[:space:]]*$//; $a\\'", stdin=file1, stdout=cmp_file1)
        subby.run("sed 's/[[:space:]]*$//; $a\\'", stdin=file2, stdout=cmp_file2)

        # diff - it would be possible to do this without sed using GNU diff with the
        # `--ignore-trailing-space` option, but unfortunately that option is not
        # available in macOS diff, which provides BSD versions of the tools by default.
        cmds = [
            f"diff -y --suppress-common-lines {cmp_file1} {cmp_file2}",
            "grep -c '^'"
        ]

        # It's a valid result to have no lines match, so allow a grep returncode of 1
        return int(subby.sub(cmds, allowed_return_codes=(0, 1)))


def assert_text_files_equal(
    file1: Path,
    file2: Path,
    allowed_diff_lines: int = 0,
    diff_fn: Callable[[Path, Path], int] = diff_default
) -> None:
    fmt = guess_file_format(file1)
    if fmt:
        with tempdir() as temp:
            temp_file1 = temp / "file1"
            temp_file2 = temp / "file2"
            transcode_file(file1, temp_file1, dest_compression=False)
            transcode_file(file2, temp_file2, dest_compression=False)
            diff_lines = diff_fn(temp_file1, temp_file2)
    else:
        diff_lines = diff_fn(file1, file2)

    if diff_lines > allowed_diff_lines:
        raise AssertionError(
            f"{diff_lines} lines (which is > {allowed_diff_lines} allowed) are "
            f"different between files {file1}, {file2}"
        )


def compare_gzip(file1: Path, file2: Path):
    crc_size1 = subby.sub(f"gzip -lv {file1} | tail -1 | awk '{{print $2\":\"$7}}'")
    crc_size2 = subby.sub(f"gzip -lv {file2} | tail -1 | awk '{{print $2\":\"$7}}'")
    if crc_size1 != crc_size2:  # TODO: test this
        raise AssertionError(
            f"CRCs and/or uncompressed sizes differ between expected identical "
            f"gzip files {file1}, {file2}"
        )


# TODO: allow user-defined comparators
BINARY_COMPARATORS = {
    "gz": compare_gzip,
    "gzip": compare_gzip
}


def assert_binary_files_equal(file1: Path, file2: Path, digest: str = "md5") -> None:
    fmt = guess_file_format(file1)
    if fmt and fmt in BINARY_COMPARATORS:
        BINARY_COMPARATORS[fmt](file1, file2)
    else:
        compare_files_with_hash(file1, file2, digest)
