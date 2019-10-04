import json
from pathlib import Path

from pytest_wdl.data_types import DataFile


class JsonDataFile(DataFile):
    def _assert_contents_equal(self, other_path: Path, other_opts: dict) -> None:
        with open(self.path, "rt") as inp:
            try:
                j1 = json.load(inp)
            except json.decoder.JSONDecodeError:
                raise AssertionError(f"Invalid JSON file {self.path}")
        with open(other_path, "rt") as inp:
            try:
                j2 = json.load(inp)
            except json.decoder.JSONDecodeError:
                raise AssertionError(f"Invalid JSON file {other_path}")
        assert j1 == j2
