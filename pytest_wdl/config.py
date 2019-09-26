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
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Dict, List, Optional, Union

from xphyle import open_

from pytest_wdl.utils import ensure_path, env_map


ENV_CACHE_DIR = "PYTEST_WDL_CACHE_DIR"
KEY_CACHE_DIR = "cache_dir"
ENV_EXECUTION_DIR = "PYTEST_WDL_EXECUTION_DIR"
KEY_EXECUTION_DIR = "execution_dir"
KEY_PROXIES = "proxies"
KEY_HTTP_HEADERS = "http_headers"
KEY_SHOW_PROGRESS = "show_progress"
ENV_DEFAULT_EXECUTORS = "PYTEST_WDL_EXECUTORS"
KEY_DEFAULT_EXECUTORS = "default_executors"
KEY_EXECUTORS = "executors"


class UserConfiguration:
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
        http_headers: A list of dicts, each of which defines a header. The allowed
            keys are 'pattern', 'name', 'env', and 'value', where pattern is a URL
            pattern to match, 'name' is the header name and 'env' and 'value' are
            interpreted the same as for `proxies`. If no pattern is provided, the
            header is used for all URLs.
        show_progress: Whether to show progress bars when downloading remote test data
            files.
        executors: Default set of executors to run.
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
        http_headers: Optional[List[dict]] = None,
        show_progress: Optional[bool] = None,
        executors: Optional[str] = None,
        executor_defaults: Optional[Dict[str, dict]] = None,
    ):
        if config_file:
            with open_(config_file, "rt") as inp:
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
            http_headers = defaults[KEY_HTTP_HEADERS]
            for d in http_headers:
                if "pattern" in d:
                    d["pattern"] = re.compile(d.pop("pattern"))
        self.default_http_headers = http_headers or []

        self.show_progress = show_progress
        if self.show_progress is None:
            self.show_progress = defaults.get(KEY_SHOW_PROGRESS)

        if not executors:
            executors_str = os.environ.get(ENV_DEFAULT_EXECUTORS)
            # TODO: test multiple executors specified by environment variable
            if executors_str:
                executors = executors_str.split(",")
            else:
                executors = defaults.get(KEY_DEFAULT_EXECUTORS, ["cromwell"])
        self.executors = executors

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
