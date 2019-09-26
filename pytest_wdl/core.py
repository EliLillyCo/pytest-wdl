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
import os
from pathlib import Path
import tempfile
from typing import Callable, List, Optional, Sequence, Type, Union, cast

from pytest_wdl.config import UserConfiguration
from pytest_wdl.data_types import DEFAULT_TYPE, DataFile, DefaultDataFile
from pytest_wdl.executors import Executor
from pytest_wdl.localizers import (
    LinkLocalizer, StringLocalizer, JsonLocalizer, UrlLocalizer
)
from pytest_wdl.url_schemes import install_schemes
from pytest_wdl.utils import ensure_path, plugin_factory_map


DATA_TYPES = plugin_factory_map(DataFile, "pytest_wdl.data_types")
"""Data type plugin modules from the discovered entry points."""

EXECUTORS = plugin_factory_map(Executor, "pytest_wdl.executors")
"""Executor plugin modules from the discovered entry points."""

# Install URL scheme plugins
install_schemes()


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
                    if self.cls:
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
    def __init__(self, data_descriptors: dict, user_config: UserConfiguration):
        self.data_descriptors = data_descriptors
        self.user_config = user_config

    def resolve(self, name: str, datadirs: Optional[DataDirs] = None):
        if name not in self.data_descriptors:
            raise ValueError(f"Unrecognized name {name}")

        value = self.data_descriptors[name]

        if isinstance(value, dict):
            # Right now, "class" is just a marker for object types, of which
            # "file" is a special case.
            cls = value.get("class", "file")
            if "value" in value:
                value = value["value"]
            if cls == "file":
                return create_data_file(
                    user_config=self.user_config,
                    datadirs=datadirs,
                    **cast(dict, value)
                )

        return value


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

    def get_list(self, *names: str) -> list:
        return [self[name] for name in names]

    def get_dict(self, *names: str, **params) -> dict:
        """
        Creates a dict with one or more entries from this DataManager.

        Args:
            *names: Names of test data entries to add to the dict.
            **params: Mapping of workflow parameter names to test data entry names.

        Returns:
            Dict mapping parameter names to test data entries for all specified names.
        """
        d = {}
        for name in names:
            d[name] = self[name]
        for param, name in params.items():
            d[param] = self[name]
        return d


def create_data_file(
    user_config: UserConfiguration,
    type: Optional[Union[str, dict]] = DEFAULT_TYPE,
    name: Optional[str] = None,
    path: Optional[Union[str, Path]] = None,
    url: Optional[str] = None,
    contents: Optional[Union[str, dict]] = None,
    env: Optional[str] = None,
    datadirs: Optional[DataDirs] = None,
    http_headers: Optional[dict] = None,
    **kwargs
) -> DataFile:
    if isinstance(type, dict):
        data_file_opts = cast(dict, type)
        type = data_file_opts.pop("name")
    else:
        data_file_opts = {}
    data_file_opts.update(kwargs)

    local_path = None
    localizer = None

    if path:
        local_path = ensure_path(path, [user_config.cache_dir])

    if local_path and local_path.exists():
        pass
    elif env and env in os.environ:
        env_path = ensure_path(os.environ[env], exists=True)
        if not local_path:
            local_path = env_path
        else:
            localizer = LinkLocalizer(env_path)
    elif url:
        localizer = UrlLocalizer(url, user_config, http_headers)
        if not local_path:
            if name:
                local_path = ensure_path(user_config.cache_dir / name)
            else:
                filename = url.rsplit("/", 1)[1]
                local_path = ensure_path(user_config.cache_dir / filename)
    elif contents:
        if isinstance(contents, str):
            localizer = StringLocalizer(cast(str, contents))
        else:
            localizer = JsonLocalizer(cast(dict, contents))
            if type == DEFAULT_TYPE:
                type = "json"
        if not local_path:
            if name:
                local_path = ensure_path(user_config.cache_dir / name)
            else:
                local_path = ensure_path(
                    tempfile.mktemp(dir=user_config.cache_dir)
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

    data_file_class = DATA_TYPES.get(type, DefaultDataFile)
    return data_file_class(local_path, localizer, **data_file_opts)


def create_executor(
    executor_name: str,
    import_dirs: Sequence[Path],
    user_config: UserConfiguration
):
    executor_class = EXECUTORS.get(executor_name)
    if not executor_class:
        raise RuntimeError(f"{executor_name} executor plugin is not installed")
    return executor_class(
        import_dirs=import_dirs,
        **user_config.get_executor_defaults(executor_name)
    )
