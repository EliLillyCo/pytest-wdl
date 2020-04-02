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
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

from _pytest.fixtures import FixtureRequest
from pytest_subtests import SubTests

from pytest_wdl import config
from pytest_wdl.config import UserConfiguration
from pytest_wdl.core import DataResolver, DataManager, DataDirs, create_executor
from pytest_wdl.utils import ensure_path, context_dir, find_project_path

try:
    import yaml
except ImportError:
    yaml = None


DEFAULT_TEST_DATA_FILE = "test_data"
DEFAULT_IMPORT_PATHS_FILE = "import_paths.txt"


def user_config_file() -> Optional[Path]:
    """
    Fixture that provides the value of 'user_config' environment variable. If
    not specified, looks in the default location ($HOME/pytest_user_config.json).

    Returns:
        Path to the confif file, or None if not specified.
    """
    return config.default_user_config_file()


def user_config(user_config_file: Optional[Path]) -> UserConfiguration:
    config.set_instance(path=user_config_file)
    yield config.get_instance()
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
    else:  # TODO: test this
        # If the project root can't be identified, fall back to the parent of
        # the current directory (which is probably tests).
        return path.parent


def workflow_data_descriptor_file(request: FixtureRequest) -> Union[str, Path]:
    """
    Fixture that provides the path to the JSON file that describes test data files.

    Args:
        request: A FixtureRequest object
    """
    test_data_files = [f"{DEFAULT_TEST_DATA_FILE}.json"]

    if yaml:
        test_data_files.append(f"{DEFAULT_TEST_DATA_FILE}.yaml")

    test_data_paths = []

    for f in test_data_files:
        test_data_paths.extend((Path(f), Path("tests") / f))

    return find_project_path(
        *test_data_files, start=Path(request.fspath.dirpath()), assert_exists=True
    )


def workflow_data_descriptors(
    request: FixtureRequest,
    project_root: Union[str, Path],
    workflow_data_descriptor_file: Union[str, Path],
) -> dict:
    """
    Fixture that provides a mapping of test data names to values. If
    workflow_data_descriptor_file is relative, it is searched first relative to the
    current test context directory and then relative to the project root.

    Args:
        workflow_data_descriptor_file: Path to the data descriptor JSON file.

    Returns:
        A dict with keys as test data names and each value either a
        primitive, a map describing a data file, or a DataFile object.
    """
    search_paths = [Path(request.fspath.dirpath()), project_root]
    workflow_data_descriptor_path = ensure_path(
        workflow_data_descriptor_file,
        search_paths=search_paths,
        is_file=True,
        exists=True,
    )
    with open(workflow_data_descriptor_path, "rt") as inp:
        if yaml and workflow_data_descriptor_path.suffix == ".yaml":
            return yaml.load(inp)
        else:
            return json.load(inp)


def workflow_data_resolver(
    workflow_data_descriptors: dict, user_config: UserConfiguration
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
    data_dirs = DataDirs(
        ensure_path(request.fspath.dirpath(), canonicalize=True),
        request.module,
        request.function,
        request.cls,
    )
    return DataManager(workflow_data_resolver, data_dirs)


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
    request: FixtureRequest,
    project_root: Union[str, Path],
    import_paths: Optional[Union[str, Path]],
) -> List[Union[str, Path]]:
    """
    Fixture that provides a list of directories containing WDL scripts to make
    avaialble as imports. Uses the file provided by `import_paths` fixture if
    it is not None, otherwise returns a list containing the parent directory
    of the test module.

    Args:
        request: A FixtureRequest object
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
        module_dir = find_project_path(
            "tests", start=Path(request.fspath.dirpath()), return_parent=True
        )

        if module_dir:
            return [module_dir]
        else:
            return []


def default_executors(user_config: UserConfiguration) -> Sequence[str]:
    return user_config.executors


def workflow_runner(
    request: FixtureRequest,
    project_root: Union[str, Path],
    import_dirs: List[Union[str, Path]],
    user_config: UserConfiguration,
    default_executors: Sequence[str],
    subtests: SubTests,
):
    """
    Provides a callable that runs a workflow. The callable has the same signature as
    `Executor.run_workflow`, but takes an additional keyword argument `executors`,
    a sequence of strings, which allows overriding the names of the executors to use.

    If multiple executors are specified, the tests are run using the `subtests`
    fixture of the `pytest-subtests` plugin.

    Args:
        request: A FixtureRequest object.
        project_root: Project root directory.
        import_dirs: Directories from which to import WDL scripts.
        user_config: A UserConfiguration object.
        default_executors: Names of executors to use when executor name isn't passed to
            the `workflow_runner` callable.
        subtests: A SubTests object.

    Returns:
        A generator over the results of calling the workflow with each executor. Each
        value is a tuple `(executor_name, execution_dir, outputs)`, where
        `execution_dir` is the root directory where the task/workflow was run (the
        structure of the directory is executor-dependent) and `outputs` is a dict of
        the task/workflow outputs.
    """
    return WorkflowRunner(
        default_executors=default_executors,
        wdl_search_paths=[Path(request.fspath.dirpath()), project_root],
        import_dirs=[ensure_path(d, is_file=False, exists=True) for d in import_dirs],
        user_config=user_config,
        subtests=subtests,
    )


class WorkflowRunner:
    """
    Callable object that runs tests.
    """
    def __init__(
        self,
        wdl_search_paths: Sequence[Path],
        import_dirs: Sequence[Path],
        user_config: UserConfiguration,
        subtests: SubTests,
        default_executors: Optional[Sequence[str]] = None
    ):
        """
        Base class for test runners.
        """
        self._wdl_search_paths = wdl_search_paths
        self._import_dirs = import_dirs
        self._user_config = user_config
        self._subtests = subtests
        self._default_executors = default_executors or ()

    def __call__(self, *args, **kwargs) -> dict:
        executors, call_args = self._args(*args, **kwargs)

        outputs = {}
        failed = []

        if len(executors) == 1:
            outputs[executors[0]] = self._run_test(executors[0], **call_args)
        else:
            for executor_name in executors:
                with self._subtests.test(executor_name=executor_name):
                    try:
                        outputs[executor_name] = self._run_test(
                            executor_name, **call_args
                        )
                    except:
                        failed.append(executor_name)
                        raise

        if failed:
            raise AssertionError(f"One or more sub-tests failed: {failed}")

        return outputs

    def _args(
        self,
        wdl_script: Union[str, Path],
        *args,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        executors: Optional[Sequence[str]] = None,
        **kwargs,
    ) -> Tuple[Sequence[str], dict]:
        """
        Handle multiple different call signatures.

        Args:
            wdl_script:
            args: Positional arguments. Supports backward-compatibility for workflows
                using the old `run_workflow` signature in which the second argument
                was the workflow name. This will be removed in the next major version.
            inputs:
            expected:
            executors:
            kwargs: Additional keyword arguments

        Returns:
            Tuple of (executors, call_kwargs).
        """
        wdl_path = ensure_path(
            wdl_script, self._wdl_search_paths, is_file=True, exists=True
        )

        if args:
            args_list = list(args)

            if isinstance(args_list[0], str):
                kwargs["workflow_name"] = args_list.pop(0)

            if args_list:
                if inputs:
                    raise TypeError("Multiple values for argument 'inputs'")

                inputs = args_list.pop(0)

                if args_list:
                    if expected:
                        raise TypeError("Multiple values for argument 'expected'")

                    expected = args_list.pop(0)

                    if args_list:
                        raise TypeError("Too many arguments")

        if not executors:
            executors = self._default_executors

        if len(executors) == 0:
            raise RuntimeError("At least one executor must be specified")

        call_args = {
            "wdl_path": wdl_path,
            "inputs": inputs,
            "expected": expected,
        }

        call_args.update(kwargs)

        return executors, call_args

    def _run_test(
        self,
        executor_name: str,
        wdl_path: Path,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        callback: Optional[Callable[[str, Path, dict], None]] = None,
        **kwargs
    ) -> dict:
        executor = create_executor(executor_name, self._import_dirs, self._user_config)

        with context_dir(
            self._user_config.default_execution_dir, change_dir=True
        ) as execution_dir:
            outputs = executor.run_workflow(
                wdl_path, inputs=inputs, expected=expected, **kwargs
            )

            if callback:
                callback(executor_name, execution_dir, outputs)

            return outputs
