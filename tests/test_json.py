import json

from pytest_wdl.data_types.json import JsonDataFile
from pytest_wdl.localizers import JsonLocalizer
from pytest_wdl.utils import tempdir


def test_json_data_type():
    with tempdir() as d:
        expected = d / "expected.json"
        actual = d / "actual.json"
        contents = {
            "foo": 1,
            "bar": "a"
        }
        with open(actual, "wt") as out:
            json.dump(contents, out)
        df = JsonDataFile(expected, JsonLocalizer(contents))
        df.assert_contents_equal(actual)
