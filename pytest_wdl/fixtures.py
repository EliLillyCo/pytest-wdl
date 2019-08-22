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

"""
Fixtures for writing tests that execute WDL workflows using Cromwell.

Note: This library is being transitioned to python3 only, and to use `pathlib.Path`s
instead of string paths. For backward compatibility fixtures that produce a path may
still return string paths, but this support will be dropped in a future version.
"""
import json
import os
from pathlib import Path
from typing import List, Optional, Union

from _pytest.fixtures import FixtureRequest

from pytest_wdl.core import (
    EXECUTORS, DataResolver, DataManager, DataDirs, Executor, UserConfiguration
)
from pytest_wdl.utils import ensure_path, context_dir, find_project_path


ENV_USER_CONFIG = "PYTEST_WDL_CONFIG"
DEFAULT_USER_CONFIG_FILE = "pytest_wdl_config.json"
DEFAULT_TEST_DATA_FILE = "test_data.json"
DEFAULT_IMPORT_PATHS_FILE = "import_paths.txt"


def user_config_file() -> Optional[Path]:
    """
    Fixture that provides the value of 'user_config' environment variable. If
    not specified, looks in the default location ($HOME/pytest_user_config.json).

    Returns:
        Path to the confif file, or None if not specified.
    """
    config_file = os.environ.get(ENV_USER_CONFIG)
    config_path = None
    if config_file:
        config_path = ensure_path(config_file)
    else:
        default_config_path = Path.home() / DEFAULT_USER_CONFIG_FILE
        if default_config_path.exists():
            config_path = default_config_path
    if config_path and not config_path.exists():
        raise FileNotFoundError(f"Config file {config_path} does not exist")
    return config_path


def user_config(user_config_file: Optional[Path]) -> UserConfiguration:
    config = UserConfiguration(user_config_file)
    yield config
    config.cleanup()


def project_root_files() -> List[str]:
    """
    Fixture that provides a list of filenames that are found in the project root
    directory. Used by the `project_root` fixture to locate the project root
    directory.
    """
    return [".git", "setup.py", "pyproject.toml"]


def project_root(
    request: FixtureRequest, project_root_files: List[str]
) -> Union[str, Path]:
    """
    Fixture that provides the root directory of the project. By default, this
    assumes that the project has one subdirectory per task, and that this
    framework is being run from the test subdirectory of a task diretory, and
    therefore looks for the project root two directories up.
    """
    path = Path(request.fspath.dirpath())
    root = find_project_path(*project_root_files, start=path, return_parent=True)
    if root:
        return root
    else:
        # If the project root can't be identified, fall back to the parent of
        # the current directory (which is probably tests).
        return path.parent


def workflow_data_descriptor_file() -> Union[str, Path]:
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    tests = find_project_path(Path("tests"))
    if tests:
        test_data = tests / DEFAULT_TEST_DATA_FILE
        if test_data.exists():
            return test_data
    raise FileNotFoundError(f"Could not find {DEFAULT_TEST_DATA_FILE} file")


def workflow_data_descriptors(workflow_data_descriptor_file: Union[str, Path]) -> dict:
    """
    Fixture that provides a mapping of test data names to values.

    Args:
        workflow_data_descriptor_file: Path to the data descriptor JSON file.

    Returns:
        A dict with keys as test data names and each value either a
        primitive, a map describing a data file, or a DataFile object.
    """
    with open(ensure_path(workflow_data_descriptor_file), "rt") as inp:
        return json.load(inp)


def workflow_data_resolver(
    workflow_data_descriptors: dict,
    user_config: UserConfiguration
) -> DataResolver:
    """
    Provides access to test data files for tests in a module.

    Args:
        workflow_data_descriptors: workflow_data_descriptors fixture.
        user_config:
    """
    return DataResolver(workflow_data_descriptors, user_config)


def workflow_data(
    request: FixtureRequest, workflow_data_resolver: DataResolver
) -> DataManager:
    """
    Provides an accessor for test data files, which may be local or in a remote
    repository.

    Args:
        request: FixtureRequest object
        workflow_data_resolver: Module-level test data configuration

    Examples:
        def workflow_data_descriptor_file():
            return "tests/test_data.json"

        def test_workflow(workflow_data):
            print(workflow_data["myfile"])
    """
    datadirs = DataDirs(
        ensure_path(request.fspath.dirpath(), canonicalize=True),
        request.module,
        request.function,
        request.cls
    )
    return DataManager(workflow_data_resolver, datadirs)


def import_paths(request: FixtureRequest) -> Union[str, Path, None]:
    """
    Fixture that provides the path to a file that lists directories containing WDL
    scripts to make available as imports. This looks for the file at
    "tests/import_paths.txt" by default, and returns None if that file doesn't exist.
    """
    import_paths_file = Path(request.fspath.dirpath()) / DEFAULT_IMPORT_PATHS_FILE
    if import_paths_file.exists():
        return import_paths_file


def import_dirs(
    project_root: Union[str, Path],
    import_paths: Optional[Union[str, Path]]
) -> List[Union[str, Path]]:
    """
    Fixture that provides a list of directories containing WDL scripts to make
    avaialble as imports. Uses the file provided by `import_paths` fixture if
    it is not None, otherwise returns a list containing the parent directory
    of the test module.

    Args:
        project_root: Project root directory
        import_paths: File listing paths to imports, one per line
    """
    if import_paths:
        import_paths = ensure_path(import_paths, canonicalize=True)
        if not import_paths.exists():
            raise FileNotFoundError(f"import_paths file {import_paths} does not exist")

        paths = []

        with open(import_paths, "rt") as inp:
            for path_str in inp.read().splitlines(keepends=False):
                path = Path(path_str)
                if not path.is_absolute():
                    path = ensure_path(project_root / path)
                if not path.exists():
                    raise FileNotFoundError(f"Invalid import path: {path}")
                paths.append(path)

        return paths
    else:
        return []


def workflow_runner(
    project_root: Union[str, Path],
    import_dirs: List[Union[str, Path]],
    user_config: UserConfiguration
):
    """
    Provides a callable that runs a workflow (with the same signature as
    `Executor.run_workflow`).

    Args:
        project_root: Project root directory.
        import_dirs: Directories from which to import WDL scripts.
        user_config:
    """
    def _run_workflow(
        wdl_script: Union[str, Path],
        workflow_name: Optional[str] = None,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        executor_name: str = "cromwell",
        **kwargs
    ):
        executor_class = EXECUTORS.get(executor_name)
        if not executor_class:
            raise RuntimeError(f"{executor_name} executor plugin is not installed")
        executor = executor_class(
            project_root=project_root,
            import_dirs=import_dirs,
            **user_config.get_executor_defaults(executor_name)
        )
        with context_dir(user_config.default_execution_dir, change_dir=True):
            executor.run_workflow(
                wdl_script, workflow_name, inputs, expected, **kwargs
            )

    return _run_workflow
