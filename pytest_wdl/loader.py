from abc import ABCMeta, abstractmethod
import json
from typing import Any, IO, Optional, Sequence, cast

from pytest_wdl.core import DataDirs, DataManager, DataResolver
from pytest_wdl.utils import ensure_path

from py.path import local
import pytest
from _pytest.fixtures import FixtureRequest

try:
    import yaml
except ImportError:
    yaml = None


def pytest_collection(session: pytest.Session):
    """
    Prints an empty line to make the report look slightly better.
    """
    print()


def pytest_collect_file(path: local, parent) -> Optional[pytest.File]:
    if path.basename.startswith("test") and not path.basename.startswith("test_data."):
        if path.ext == ".json":
            return JsonWdlTestsModule(path, parent)
        elif yaml and path.ext == ".yaml":
            return YamlWdlTestsModule(path, parent)


# TODO: the Node API will be changing at some point
# https://docs.pytest.org/en/latest/example/nonpython.html#a-basic-example-for-specifying-tests-in-yaml-files


class WdlTestsModule(pytest.Module, metaclass=ABCMeta):
    @abstractmethod
    def _load(self, fp: IO) -> dict:
        pass

    def collect(self):
        with self.fspath.open() as inp:
            d = self._load(inp)

        if "tests" not in d:
            raise ValueError(f"Tests file {self.fspath} must contain a 'tests' key")

        data = d.get("data")

        for spec in d["tests"]:
            if "name" not in spec:
                raise ValueError("Test case missing 'name' key")

            yield TestItem(self, data=data, **spec)


class YamlWdlTestsModule(WdlTestsModule):
    def _load(self, fp: IO) -> dict:
        return yaml.safe_load(fp)


class JsonWdlTestsModule(WdlTestsModule):
    def _load(self, fp: IO) -> dict:
        return json.load(fp)


class TestItem(pytest.Item):
    def __init__(
        self,
        parent,
        data: Optional[dict] = None,
        name: Optional[str] = None,
        wdl: Optional[str] = None,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        tags: Optional[Sequence] = None,
        **kwargs
    ):
        if not all((name, wdl)):
            raise ValueError("Every test must have 'name' and 'wdl' keys")

        super().__init__(name, parent)
        self._wdl = wdl
        self._inputs = inputs
        self._expected = expected
        self._tags = tags  # TODO: add tags as marks
        self._workflow_runner_kwargs = kwargs
        self._data = data
        self._fixture_request = None

    def setup(self):
        """
        This method is black magic - uses internal pytest APIs to create a
        FixtureRequest that can be used to access fixtures in `runtest()`.
        Copied from
        https://github.com/pytest-dev/pytest/blob/master/src/_pytest/doctest.py.
        """
        def func():
            pass

        self.funcargs = {}
        fm = self.session._fixturemanager
        self._fixtureinfo = fm.getfixtureinfo(
            node=self, func=func, cls=None, funcargs=False
        )
        self._fixture_request = FixtureRequest(self)
        self._fixture_request._fillfixtures()

    def runtest(self):
        # Get/create DataManager
        if self._data:
            config = self._fixture_request.getfixturevalue("user_config")
            data_resolver = DataResolver(self._data, config)
            data_dirs = DataDirs(
                ensure_path(self._fixture_request.fspath.dirpath(), canonicalize=True),
                function=self.name,
                module=None,  # TODO: support a top-level key for module name
                cls=None,  # TODO: support test groupings
            )
            workflow_data = DataManager(data_resolver, data_dirs)
        else:
            workflow_data = self._fixture_request.getfixturevalue("workflow_data")

        # Build the arguments to workflow_runner
        workflow_runner_kwargs = self._workflow_runner_kwargs

        # Resolve test data requests in the inputs and outputs

        if self._inputs:
            workflow_runner_kwargs["inputs"] = _resolve_test_data(
                self._inputs, workflow_data
            )

        if self._expected:
            workflow_runner_kwargs["expected"] = _resolve_test_data(
                self._expected, workflow_data
            )

        # Run the test
        workflow_runner = self._fixture_request.getfixturevalue("workflow_runner")

        return workflow_runner(self._wdl, **workflow_runner_kwargs)


def _resolve_test_data(d: dict, workflow_data: DataManager) -> dict:
    def _resolve(val: Any):
        if isinstance(val, str):
            try:
                # See if it's a test data entry
                return workflow_data[cast(str, val)]
            except FileNotFoundError:
                # It's a string literal
                return val
        elif isinstance(val, dict):
            return dict((key, _resolve(value)) for key, value in cast(dict, d).items())
        elif isinstance(val, Sequence):
            return [_resolve(value) for value in cast(Sequence, val)]
        else:
            return val

    return _resolve(d)
