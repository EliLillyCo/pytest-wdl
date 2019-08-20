from abc import ABCMeta, abstractmethod
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable, Dict, List, Optional, Pattern, Type, Union, cast
from urllib import request

import delegator

from pytest_wdl.utils import (
    LOG, tempdir, ensure_path, plugin_factory_map, env_map,
    resolve_value_descriptor
)


ENV_CACHE_DIR = "PYTEST_WDL_CACHE_DIR"
KEY_CACHE_DIR = "cache_dir"
ENV_EXECUTION_DIR = "PYTEST_WDL_EXECUTION_DIR"
KEY_EXECUTION_DIR = "execution_dir"
KEY_PROXIES = "proxies"
KEY_HTTP_HEADERS = "http_headers"
KEY_EXECUTORS = "executors"


class WdlConfig:
    """
    Stores pytest-wdl configuration. If configuration options are specified both in
    the config file and as arguments to the constructor, the latter take precedence.

    Args:
        config_file: JSON file from which to load default values.
        cache_dir: The directory in which to cache localized files; defaults to using
            a temporary directory that is specific to each module and deleted
            afterwards.
        remove_cache_dir: Whether to remove the cache directory; if None, takes the
            value True if a temp directory is used for caching, and False, if
            a value for `cache_dir` is specified.
        execution_dir: The directory in which to run workflows. Defaults to None,
            which signals that a different temporary directory should be used for
            each workflow run.
        proxies: Mapping of proxy type (typically 'http' or 'https' to either an
            environment variable, or a dict with either/both keys 'env' and 'value',
            where the value is taken from the environment variable ('env') first, and
            from 'value' if the environment variable is not specified or is unset.
        http_headers: A mapping of URI pattern to dict with keys 'name', 'env', 'value',
            where 'name' is the header name and 'env' and 'value' are interpreted the
            same as for `proxies`.
        executor_defaults: Mapping of executor name to dict of executor-specific
            configuration options.
    """
    def __init__(
        self,
        config_file: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        remove_cache_dir: Optional[bool] = None,
        execution_dir: Optional[Path] = None,
        proxies: Optional[Dict[str, Union[str, Dict[str, str]]]] = None,
        http_headers: Optional[Dict[Pattern, Dict[str, str]]] = None,
        executor_defaults: Optional[Dict[str, dict]] = None,
    ):
        if config_file:
            with open(config_file, "rt") as inp:
                defaults = json.load(inp)
        else:
            defaults = {}

        if not cache_dir:
            cache_dir_str = os.environ.get(ENV_CACHE_DIR, defaults.get(KEY_CACHE_DIR))
            if cache_dir_str:
                cache_dir = ensure_path(cache_dir_str)
        if cache_dir:
            self.cache_dir = ensure_path(cache_dir, is_file=False, create=True)
            if remove_cache_dir is None:
                remove_cache_dir = False
        else:
            self.cache_dir = Path(tempfile.mkdtemp())
            if remove_cache_dir is None:
                remove_cache_dir = True
        self.remove_cache_dir = remove_cache_dir

        if not execution_dir:
            execution_dir_str = os.environ.get(
                ENV_EXECUTION_DIR, defaults.get(KEY_EXECUTION_DIR)
            )
            if execution_dir_str:
                execution_dir = ensure_path(execution_dir_str)
        if execution_dir:
            self.default_execution_dir = ensure_path(
                execution_dir, is_file=False, create=True
            )
        else:
            self.default_execution_dir = None

        if not proxies and KEY_PROXIES in defaults:
            proxies = env_map(defaults[KEY_PROXIES])
        self.proxies = proxies or {}

        if not http_headers and KEY_HTTP_HEADERS in defaults:
            http_headers = {
                re.compile(d["pattern"]): d
                for d in defaults[KEY_HTTP_HEADERS]
            }
        self.default_http_headers = http_headers or {}

        self.executor_defaults = executor_defaults or {}
        if "executors" in defaults:
            for name, d in defaults["executors"].items():
                if name not in self.executor_defaults:
                    self.executor_defaults[name] = d

    def get_executor_defaults(self, executor_name: str) -> dict:
        """
        Get default configuration values for the given executor.

        Args:
            executor_name: The executor name

        Returns:
            A dict with the executor configuration values, if any.
        """
        return self.executor_defaults.get(executor_name, {})

    def cleanup(self) -> None:
        """
        Preforms cleanup operations, such as deleting the cache directory if
        `self.remove_cache_dir` is True.
        """
        if self.remove_cache_dir:
            shutil.rmtree(self.cache_dir)


class Localizer(metaclass=ABCMeta):  # pragma: no-cover
    """
    Abstract base of classes that implement file localization.
    """
    @abstractmethod
    def localize(self, destination: Path) -> None:
        """
        Localize a resource to `destination`.

        Args:
            destination: Path to file where the non-local resource is to be localized.
        """
        pass


class UrlLocalizer(Localizer):
    """
    Localizes a file specified by a URL.
    """
    def __init__(
        self, url: str, wdl_config: WdlConfig, http_headers: Optional[dict] = None
    ):
        self.url = url
        self.wdl_config = wdl_config
        self.http_headers = http_headers

    def localize(self, destination: Path):
        LOG.debug(f"Localizing url %s to %s", self.url, str(destination))
        try:
            req = request.Request(self.url)
            self.add_http_headers(req)
            self.set_proxies(req)
            rsp = request.urlopen(req)
            with open(destination, "wb") as out:
                shutil.copyfileobj(rsp, out)
        except Exception as err:
            raise RuntimeError(f"Error localizing url {self.url}") from err

    def add_http_headers(self, req: request.Request):
        http_headers = {}

        if self.http_headers:
            http_headers.update(env_map(self.http_headers))

        if self.wdl_config.default_http_headers:
            for pattern, value_dict in self.wdl_config.default_http_headers.items():
                name = value_dict.get("name")
                if name not in http_headers and pattern.match(self.url):
                    value = resolve_value_descriptor(value_dict)
                    if value:
                        http_headers[name] = value

        if http_headers:
            for name, value in http_headers.items():
                req.add_header(name, value)

    def set_proxies(self, req: request.Request):
        proxies = self.wdl_config.proxies
        if proxies:
            for proxy_type, url in proxies.items():
                req.set_proxy(url, proxy_type)


class StringLocalizer(Localizer):
    """
    Localizes a string by writing it to a file.
    """
    def __init__(self, contents: str):
        self.contents = contents

    def localize(self, destination: Path):
        LOG.debug(f"Persisting {destination} from contents")
        with open(destination, "wt") as out:
            out.write(self.contents)


class LinkLocalizer(Localizer):
    """
    Localizes a file to another destination using a symlink.
    """
    def __init__(self, source: Path):
        self.source = source

    def localize(self, destination: Path):
        destination.symlink_to(self.source)


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


DATA_TYPES = plugin_factory_map("pytest_wdl.data_types", DataFile)
"""Data type plugin modules from the discovered entry points."""


class DataDirs:
    """
    Provides data files from test data directory structure as defined by the
    datadir and datadir-ng plugins. Paths are resolved lazily upon first request.
    """
    def __init__(
        self,
        basedir: Path,
        module,  # TODO: no Module type in typelib yet
        function: Callable,
        cls: Optional[Type] = None
    ):
        module_path = module.__name__.split(".")
        if len(module_path) > 1:
            for mod in reversed(module_path[:-1]):
                if basedir.name == mod:
                    basedir = basedir.parent
                else:
                    raise RuntimeError(
                        f"Module path {module_path} does not match basedir {basedir}"
                    )
        self.basedir = basedir
        self.module = os.path.join(*module_path)
        self.function = function.__name__
        self.cls = cls.__name__ if cls else None
        self._paths = None

    @property
    def paths(self) -> List[Path]:
        if self._paths is None:
            def add_datadir_paths(root: Path):
                testdir = root / self.module
                if testdir.exists():
                    if self.cls is not None:
                        clsdir = testdir / self.cls
                        if clsdir.exists():
                            fndir = clsdir / self.function
                            if fndir.exists():
                                self._paths.append(fndir)
                            self._paths.append(clsdir)
                    else:
                        fndir = testdir / self.function
                        if fndir.exists():
                            self._paths.append(fndir)
                    self._paths.append(testdir)

            self._paths = []
            add_datadir_paths(self.basedir)
            data_root = self.basedir / "data"
            if data_root.exists():
                add_datadir_paths(data_root)
                self._paths.append(data_root)

        return self._paths


class DataResolver:
    """
    Resolves data files that may need to be localized.
    """
    def __init__(self, data_descriptors: dict, wdl_config: WdlConfig):
        self.data_descriptors = data_descriptors
        self.wdl_config = wdl_config

    def resolve(
        self, name: str, datadirs: Optional[DataDirs] = None
    ) -> DataFile:
        if name not in self.data_descriptors:
            raise ValueError(f"Unrecognized name {name}")

        value = self.data_descriptors[name]
        if isinstance(value, dict):
            return self.create_data_file(datadirs=datadirs, **cast(dict, value))
        else:
            return value

    def create_data_file(
        self,
        type: Optional[str] = "default",
        name: Optional[str] = None,
        path: Optional[str] = None,
        url: Optional[str] = None,
        contents: Optional[str] = None,
        datadirs: Optional[DataDirs] = None,
        http_headers: Optional[dict] = None,
        **kwargs
    ) -> DataFile:
        data_file_class = DATA_TYPES.get(type, DataFile)
        local_path = None
        localizer = None

        if path:
            local_path = ensure_path(path, self.wdl_config.cache_dir)

        if url:
            localizer = UrlLocalizer(url, self.wdl_config, http_headers)
            if not local_path:
                if name:
                    local_path = ensure_path(self.wdl_config.cache_dir / name)
                else:
                    filename = url.rsplit("/", 1)[1]
                    local_path = ensure_path(self.wdl_config.cache_dir / filename)
        elif contents:
            localizer = StringLocalizer(contents)
            if not local_path:
                if name:
                    local_path = ensure_path(self.wdl_config.cache_dir / name)
                else:
                    local_path = ensure_path(
                        tempfile.mktemp(dir=self.wdl_config.cache_dir)
                    )
        elif name and datadirs:
            for dd in datadirs.paths:
                dd_path = dd / name
                if dd_path.exists():
                    break
            else:
                raise FileNotFoundError(
                    f"File {name} not found in any of the following datadirs: "
                    f"{datadirs.paths}"
                )
            if not local_path:
                local_path = dd_path
            else:
                localizer = LinkLocalizer(dd_path)
        else:
            raise FileNotFoundError(
                f"File {path or name} does not exist. Either a url, file contents, "
                f"or a local file must be provided."
            )

        return data_file_class(local_path, localizer, **kwargs)


class DataManager:
    """
    Manages test data, which is defined in a test_data.json file.

    Args:
        data_resolver: Module-level config.
        datadirs: Data directories to search for the data file.
    """
    def __init__(self, data_resolver: DataResolver, datadirs: DataDirs):
        self.data_resolver = data_resolver
        self.datadirs = datadirs

    def __getitem__(self, name: str):
        return self.data_resolver.resolve(name, self.datadirs)

    def get_dict(self, *names: str) -> dict:
        """
        Creates a dict with one or more entries from this DataManager.

        Args:
            *names: Names of test data entries to add to the dict.

        Returns:
            Dict mapping `name` to `self[name]` for all specified names.
        """
        return {name: self[name] for name in names}


class Executor(metaclass=ABCMeta):
    """
    Base class for WDL workflow executors.
    """
    @abstractmethod
    def run_workflow(
        self,
        wdl_script: Union[str, Path],
        workflow_name: Optional[str] = None,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        Run a WDL workflow on given inputs, and check that the output matches
        given expected values.

        Args:
            wdl_script: The WDL script to execute.
            workflow_name: The name of the workflow in the WDL script. If None, the
                name of the WDL script is used (without the .wdl extension).
            inputs: Object that will be serialized to JSON and provided to Cromwell
                as the workflow inputs.
            expected: Dict mapping output parameter names to expected values.
            kwargs: Additional keyword arguments, mostly for debugging:
                * execution_dir: DEPRECATED
                * inputs_file: Path to the Cromwell inputs file to use. Inputs are
                    written to this file only if it doesn't exist.
                * imports_file: Path to the WDL imports file to use. Imports are
                    written to this file only if it doesn't exist.
                * java_args: Additional arguments to pass to Java runtime.
                * cromwell_args: Additional arguments to pass to `cromwell run`.

        Returns:
            Dict of outputs.

        Raises:
            Exception: if there was an error executing the workflow
            AssertionError: if the actual outputs don't match the expected outputs
        """


EXECUTORS = plugin_factory_map("pytest_wdl.executors", Executor)
"""Executor plugin modules from the discovered entry points."""
