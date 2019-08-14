from abc import ABCMeta, abstractmethod
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, List, Optional, Tuple, Type, Union, cast
import urllib.request

import delegator

from pytest_wdl.utils import LOG, tempdir, to_path, canonical_path, plugin_factory_map


class WdlConfig:
    def __init__(self, config_file: Optional[Path] = None, **kwargs):
        self.config_file = config_file
        if config_file:
            with open(config_file, "rt") as inp:
                self._config = json.load(inp)
                self._config.update(kwargs)
        else:
            self._config = kwargs
        self._proxies = None
        self._http_headers = None

    @property
    def default_proxies(self) -> dict:
        if self._proxies is None:
            if "proxies" in self._config:
                self._proxies = envmap(self._config["proxies"])
            else:
                self._proxies = {}

        return self._proxies

    @property
    def default_http_headers(self) -> dict:
        if self._http_headers is None:
            if "http_headers" in self._config:
                self._http_headers = envmap(self._config["http_headers"])
            else:
                self._http_headers = {}

        return self._http_headers

    def get_executor_defaults(self, executor_name: str) -> dict:
        if "executors" in self._config:
            return self._config["executors"].get(executor_name)


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
        self, url: str,
        http_headers: Optional[dict] = None,
        proxies: Optional[dict] = None
    ):
        self.url = url
        self.http_headers = http_headers
        self.proxies = proxies

    def localize(self, destination: Path):
        LOG.debug(
            f"Localizing url %s to %s with headers %s and proxies %s",
            self.url, str(destination), str(self.http_headers), str(self.proxies)
        )
        try:
            req = urllib.request.Request(self.url)
            if self.http_headers:
                for name, value in self.http_headers.items():
                    req.add_header(name, value)
            if self.proxies:
                for proxy_type, url in self.proxies.items():
                    req.set_proxy(url, proxy_type)
            rsp = urllib.request.urlopen(req)
            with open(destination, "wb") as out:
                shutil.copyfileobj(rsp, out)
        except Exception as err:
            raise RuntimeError(f"Error localizing url {self.url}") from err


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


DATA_TYPES  = plugin_factory_map("pytest_wdl.data_type", DataFile)
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
                print(f"Checking {testdir}")
                if testdir.exists():
                    if self.cls is not None:
                        clsdir = testdir / self.cls
                        print(f"Checking {clsdir}")
                        if clsdir.exists():
                            fndir = clsdir / self.function
                            print(f"Checking {fndir}")
                            if fndir.exists():
                                self._paths.append(fndir)
                            self._paths.append(clsdir)
                    else:
                        fndir = testdir / self.function
                        print(f"Checking {fndir}")
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

        self.cache_dir = cache_dir
        self.http_headers = http_headers
        self.proxies = proxies

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
        **kwargs
    ) -> DataFile:
        data_file_class = DATA_TYPES.get(type, DataFile)
        local_path = None
        localizer = None

        if path:
            local_path = to_path(path, self.cache_dir)

        if url:
            localizer = UrlLocalizer(url, self.http_headers, self.proxies)
            if not local_path:
                if name:
                    local_path = canonical_path(self.cache_dir / name)
                else:
                    filename = url.rsplit("/", 1)[1]
                    local_path = canonical_path(self.cache_dir / filename)
        elif contents:
            localizer = StringLocalizer(contents)
            if not local_path:
                if name:
                    local_path = canonical_path(self.cache_dir / name)
                else:
                    local_path = canonical_path(
                        Path(tempfile.mktemp(dir=self.cache_dir))
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

    def __getitem__(self, name):
        return self.data_resolver.resolve(name, self.datadirs)


class Executor(metaclass=ABCMeta):
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
