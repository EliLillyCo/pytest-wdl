"""
Fixtures for writing tests that execute WDL workflows using Cromwell.

Note: This library is being transitioned to python3 only, and to use `pathlib.Path`s
instead of string paths. For backward compatibility fixtures that produce a path may
still return string paths, but this support will be dropped in a future version.
"""
import os
from pathlib import Path
from typing import List, Optional, Union

from _pytest.fixtures import FixtureRequest

from pytest_cromwell.core import CromwellHarness, TestDataResolver, TestData, DataDirs
from pytest_cromwell.utils import (
    LOG, chdir, to_path, test_dir, find_project_path, find_executable_path,
    canonical_path, env_map
)


def project_root_files() -> List[str]:
    """
    Fixture that provides a list of filenames that are found in the project root
    directory. Used by the `project_root` fixture to locate the project root
    directory.
    """
    return [".git", "requirements.txt", "setup.py", "pyproject.toml"]


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


def test_data_file() -> Union[str, Path]:
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    tests = find_project_path(Path("tests"))
    if tests:
        test_data = tests / "test_data.json"
        if test_data.exists():
            return test_data
    raise FileNotFoundError("Could not find test_data.json file")


def test_data_dir(project_root: Union[str, Path]) -> Union[str, Path]:
    """
    Fixture that provides the directory in which to cache the test data. If the
    "TEST_DATA_DIR" environment variable is set, the value will be used as the
    execution directory path, otherwise a temporary directory is used.

    Args:
        project_root: The root directory to use when the test data directory is
            specified as a relative path.
    """
    with test_dir("TEST_DATA_DIR", project_root) as data_dir:
        yield data_dir


def test_execution_dir(project_root: Union[str, Path]) -> Union[str, Path]:
    """
    Fixture that provides the directory in which the test is to be executed. If the
    "EXECUTION_DIR" environment variable is set, the value will be used as the
    execution directory path, otherwise a temporary directory is used.

    Args:
        project_root: The root directory to use when the execution directory is
            specified as a relative path.
    """
    with test_dir("TEST_EXECUTION_DIR", project_root) as execution_dir:
        yield execution_dir


def http_header_map() -> dict:
    """
    Fixture that provides a mapping from HTTP header name to the environment variable
    from which the value should be retrieved.
    """
    return {}


def http_headers(http_header_map: dict) -> dict:
    """
    Fixture that provides request HTTP headers to use when downloading files.
    """
    return env_map(http_header_map)


def proxy_map() -> dict:
    """
    Fixture that provides a mapping from proxy name to the environment variable
    from which the value should be retrieved.
    """
    return {}


def proxies(proxy_map: dict) -> dict:
    """
    Fixture that provides the proxies to use when downloading files.
    """
    return env_map(proxy_map)


def import_paths() -> Union[str, Path, None]:
    """
    Fixture that provides the path to a file that lists directories containing WDL
    scripts to make avaialble as imports. This looks for the file at
    "tests/import_paths.txt" by default, and returns None if that file doesn't exist.
    """
    return find_project_path(Path("tests") / "import_paths.txt")


def import_dirs(
    request: FixtureRequest,
    project_root: Union[str, Path],
    import_paths: Optional[Union[str, Path]]
) -> List[Union[str, Path]]:
    """
    Fixture that provides a list of directories containing WDL scripts to make
    avaialble as imports. Uses the file provided by `import_paths` fixture if
    it is not None, otherwise returns a list containing the parent directory
    of the test module.

    Args:
        request: FixtureRequest object
        project_root: Project root directory
        import_paths: File listing paths to imports, one per line
    """
    if import_paths:
        import_paths = to_path(import_paths)
        if not import_paths.exists():
            raise FileNotFoundError(f"import_paths file {import_paths} does not exist")

        paths = []

        with open(import_paths, "rt") as inp:
            for path_str in inp.read().splitlines(keepends=False):
                path = Path(path_str)
                if not path.is_absolute():
                    path = canonical_path(project_root / path)
                if not path.exists():
                    raise FileNotFoundError(f"Invalid import path: {path}")
                paths.append(path)

        return paths
    else:
        # Fall back to importing the WDL files in the parent of the current directory
        return [Path(request.fspath.dirpath()).parent]


def java_bin() -> Union[str, Path]:
    """
    Fixture that provides the path to the java binary.
    """
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        path = to_path(java_home, canonicalize=True)
        if not path.exists():
            raise FileNotFoundError(f"JAVA_HOME directory {path} does not exist")
        bin_path = path / "bin" / "java"
    else:
        bin_path = find_executable_path("java")

    if not (bin_path and bin_path.exists()):
        raise FileNotFoundError(f"java executable not found at {bin_path}")

    return bin_path


def cromwell_config_file() -> Union[str, Path, None]:
    """
    Fixture that returns the path to a cromwell config file, if any. By default
    it looks for the CROMWELL_CONFIG_FILE environment variable.
    """
    config_file = os.environ.get("CROMWELL_CONFIG_FILE")
    if config_file:
        path = Path(config_file)
        if not path.exists():
            raise FileNotFoundError(f"CROMWELL_CONFIG_FILE {path} does not exist")
        return path
    else:
        return None


def java_args(cromwell_config_file: Optional[Union[str, Path]] = None) -> Optional[str]:
    if cromwell_config_file:
        if cromwell_config_file.exists():
            return f"-Dconfig.file={cromwell_config_file}"
        else:
            raise FileNotFoundError(
                f"Cromwell config file not found: {cromwell_config_file}"
            )


def cromwell_jar_file() -> Union[str, Path]:
    """
    Fixture that provides the path to the Cromwell JAR file. First looks for the
    CROMWELL_JAR environment variable, then searches the classpath for a JAR file
    whose name starts with "cromwell". Defaults to "cromwell.jar" in the current
    directory.
    """
    cromwell_jar = os.environ.get("CROMWELL_JAR")
    if cromwell_jar:
        path = Path(cromwell_jar)
        if not path.exists():
            raise FileNotFoundError(f"CROMWELL_JAR directory {path} does not exist")
        return path

    classpath = os.environ.get("CLASSPATH", ".")

    for path_str in classpath.split(os.pathsep):
        path = canonical_path(Path(path_str))
        if path.exists():
            if path.is_dir():
                matches = list(path.glob("cromwell*.jar"))
                if matches:
                    if len(matches) > 1:
                        LOG.warning(
                            "Found multiple cromwell jar files: %s; returning "
                            "the first one.", matches
                        )
                    return matches[0]
            elif (
                path.suffix == ".jar" and
                path.name.lower().startswith("cromwell")
            ):
                return path

    raise FileNotFoundError(f"Cromwell JAR file not found on CLASSPATH {classpath}")


def cromwell_args() -> Optional[str]:
    return os.environ.get("CROMWELL_ARGS")


def test_data_resolver(
    test_data_file: Union[str, Path],
    test_data_dir: Union[str, Path],
    http_headers: Optional[dict] = None,
    proxies: Optional[dict] = None
) -> TestDataResolver:
    """
    Provides access to test data files for tests in a module.

    Args:
        test_data_dir: test_data_dir fixture.
        test_data_file: test_data_file fixture.
        http_headers: http_headers fixture.
        proxies: proxies fixture.
    """
    return TestDataResolver(
        to_path(test_data_file),
        to_path(test_data_dir),
        http_headers,
        proxies
    )


def test_data(
    request: FixtureRequest, test_data_resolver: TestDataResolver
) -> TestData:
    """
    Provides an accessor for test data files, which may be local or in a remote
    repository.

    Args:
        request: FixtureRequest object
        test_data_resolver: Module-level test data configuration

    Examples:
                def test_data_file():
            return "tests/test_data.json"

        def test_workflow(test_data):
            print(test_data["myfile"])
    """
    datadirs = DataDirs(
        to_path(request.fspath.dirpath(), canonicalize=True),
        request.module,
        request.function,
        request.cls
    )
    return TestData(test_data_resolver, datadirs)


def cromwell_harness(
    project_root: Union[str, Path],
    import_dirs: List[Union[str, Path]],
    java_bin: Union[str, Path],
    java_args: Optional[str],
    cromwell_jar_file: Union[str, Path],
    cromwell_args: Optional[str]
) -> CromwellHarness:
    """
    Provides a harness for calling Cromwell on WDL scripts.

    Args:
        project_root: Project root directory.
        import_dirs: Directories from which to import WDL scripts.
        java_bin: Java executable.
        java_args: String with arguments (e.g. -Dfoo=bar) to pass to Java.
        cromwell_jar_file: Path to Cromwell jar file.
        cromwell_args: String with arguments to pass to Cromwell.

    Examples:
        def test_workflow(cromwell_harness):
            cromwell_harness.run_workflow(...)
    """
    return CromwellHarness(
        project_root=to_path(project_root),
        import_dirs=list(to_path(d) for d in import_dirs),
        java_bin=to_path(java_bin),
        java_args=java_args,
        cromwell_jar_file=to_path(cromwell_jar_file),
        cromwell_args=cromwell_args
    )


def workflow_runner(
    cromwell_harness: CromwellHarness, test_execution_dir: Union[str, Path]
):
    """
    Provides a callable that runs a workflow (with the same signature as
    `CromwellHarness.run_workflow`) with the execution_dir being the one
    provided by the `test_execution_dir` fixture.
    """
    def _run_workflow(
        wdl_script: Union[str, Path],
        workflow_name: str,
        inputs: dict,
        expected: Optional[dict] = None,
        **kwargs
    ):
        with chdir(to_path(test_execution_dir)):
            cromwell_harness.run_workflow(
                wdl_script, workflow_name, inputs, expected, **kwargs
            )
    return _run_workflow
