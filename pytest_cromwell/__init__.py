#! /usr/bin/env python
"""
Fixtures for writing tests that execute WDL workflows using Cromwell.

Todo:
    * Currently a very specific directory structure is required for this
      framework to work by default. This should be generalized so that
      the structure can be defined by a config file or a session-level
      fixture.
    * Decide if this should be python3 only. If so, add type annotations and
      switch to using pathlib.Paths. Otherwise get rid of the f-strings.
"""
import os

import pytest
from _pytest.fixtures import FixtureRequest

from pytest_cromwell.core import (
    CromwellHarness, TestDataResolver, TestData, DataDirs, DataFile
)
from pytest_cromwell.utils import (
    LOG, chdir, deprecated, pypath_to_path, test_dir, tempdir
)


@pytest.fixture(scope="module")
def project_root(request: FixtureRequest):
    """
    Fixture that provides the root directory of the project. By default, this
    assumes that the project has one subdirectory per task, and that this
    framework is being run from the test subdirectory of a task diretory, and
    therefore looks for the project root two directories up.
    """
    return os.path.abspath(os.path.join(request.fspath.dirpath(), "../.."))


@pytest.fixture(scope="module")
def test_data_file():
    """
    Fixture that provides the path to the JSON file that describes test data files.
    """
    return "tests/test_data.json"


@pytest.fixture(scope="module")
def test_data_dir(project_root):
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


@pytest.fixture(scope="function")
def test_execution_dir(project_root):
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


@pytest.fixture(scope="session")
@deprecated
def default_env():
    """
    No longer used.
    """
    return None


@pytest.fixture(scope="session")
def http_header_map():
    """
    Fixture that provides a mapping from HTTP header name to the environment variable
    from which the value should be retrieved.
    """
    return {"X-JFrog-Art-Api": "TOKEN"}


@pytest.fixture(scope="session")
def http_headers(http_header_map):
    """
    Fixture that provides request HTTP headers to use when downloading files.
    """
    return _env_map(http_header_map)


@pytest.fixture(scope="session")
def proxy_map():
    """
    Fixture that provides a mapping from proxy name to the environment variable
    from which the value should be retrieved.
    """
    return {
        "http": "HTTP_PROXY",
        "https": "HTTPS_PROXY"
    }


@pytest.fixture(scope="session")
def proxies(proxy_map):
    """
    Fixture that provides the proxies to use when downloading files.
    """
    return _env_map(proxy_map)


def _env_map(key_env_map):
    """
    Given a mapping of keys to environment variables, creates a mapping of the keys
    to the values of those environment variables (if they are set).
    """
    env_map = {}
    for name, ev in key_env_map.items():
        value = os.environ.get(ev, None)
        if value:
            env_map[name] = value
    return env_map


@pytest.fixture(scope="module")
def import_paths():
    """
    Fixture that provides the path to a file that lists directories containing WDL
    scripts to make avaialble as imports. This looks for the file at
    "tests/import_paths.txt" by default, and returns None if that file doesn't exist.
    """
    default_path = "tests/import_paths.txt"
    if os.path.exists(default_path):
        return default_path
    return None


@pytest.fixture(scope="module")
def import_dirs(request, import_paths):
    """
    Fixture that provides a list of directories containing WDL scripts to make
    avaialble as imports. Uses the file provided by `import_paths` fixture if
    it is not None, otherwise returns a list containing the parent directory
    of the test module.

    Args:
        request:
        import_paths:
    """
    if import_paths:
        with open(import_paths, "rt") as inp:
            return inp.read().splitlines(keepends=False)
    else:
        parent = os.path.abspath(os.path.join(os.path.dirname(request.fspath), ".."))
        return [os.path.basename(parent)]


@pytest.fixture(scope="session")
def java_bin():
    """
    Fixture that provides the path to the java binary.
    """
    return os.path.join(
        os.path.abspath(os.environ.get("JAVA_HOME", "/usr")),
        "bin", "java"
    )


@pytest.fixture(scope="session")
def cromwell_config_file():
    """
    Fixture that returns the path to a cromwell config file, if any. By default
    it looks for the CROMWELL_CONFIG_FILE environment variable.
    """
    return os.environ.get("CROMWELL_CONFIG_FILE", None)


@pytest.fixture(scope="session")
def java_args(cromwell_config_file):
    if cromwell_config_file:
        return "-Dconfig.file={}".format(cromwell_config_file)
    else:
        return "-Ddocker.hash-lookup.enabled=false"


@pytest.fixture(scope="session")
def cromwell_jar_file():
    """
    Fixture that provides the path to the Cromwell JAR file. First looks for the
    CROMWELL_JAR environment variable, then searches the classpath for a JAR file
    whose name starts with "cromwell". Defaults to "cromwell.jar" in the current
    directory.
    """
    if "CROMWELL_JAR" in os.environ:
        return os.environ.get("CROMWELL_JAR")

    classpath = os.environ.get("CLASSPATH")
    if classpath:
        for path in classpath.split(os.pathsep):
            if os.path.basename(path).lower().startswith("cromwell"):
                return path

    return "cromwell.jar"


@pytest.fixture(scope="session")
def cromwell_args():
    return os.environ.get("CROMWELL_ARGS", None)


@pytest.fixture(scope="module")
def test_data_config(
    test_data_file, test_data_dir, http_headers, proxies
) -> TestDataResolver:
    """
    Provides access to test data files for tests in a module.

    Args:
        test_data_file: test_data_file fixture.
        test_data_dir: test_data_dir fixture.
        http_headers: http_headers fixture.
        proxies: proxies fixture.
    """
    return TestDataResolver(
        test_data_file,
        localize_dir=test_data_dir,
        http_headers=http_headers,
        proxies=proxies
    )


@pytest.fixture(scope="function")
def test_data(
    request: FixtureRequest, test_data_resolver: TestDataResolver
) -> TestData:
    """
    Provides an accessor for test data files, which may be local or in a remote
    repository.

    Args:
        request: Fixture request
        test_data_resolver: Module-level test data configuration

    Examples:
        @pytest.fixture(scope="session")
        def test_data_file():
            return "tests/test_data.json"

        def test_workflow(test_data):
            print(test_data["myfile"])
    """
    datadirs = DataDirs(
        pypath_to_path(request.fspath.dirpath()),
        request.module,
        request.cls,
        request.function
    )
    return TestData(test_data_resolver, datadirs)


@pytest.fixture(scope="module")
def cromwell_harness(
    project_root, import_dirs, java_bin, java_args, cromwell_jar_file, cromwell_args
):
    """
    Provides a harness for calling Cromwell on WDL scripts. Accepts an `import_dirs`
    argument, which is provided by a `@pytest.mark.parametrize` decoration. The
    import_dirs file contains a list of directories (one per line) that contain WDL
    files that should be made available as imports to the running WDL workflow.

    Args:
        project_root: project_root fixture.
        import_dirs: import_dirs fixture.
        java_bin: java_bin fixture.
        java_args: String with arguments (e.g. -Dfoo=bar) to pass to Java.
        cromwell_jar_file: cromwell_jar_file fixture.
        cromwell_args: String with arguments to pass to Cromwell.

    Examples:
        def test_workflow(cromwell_harness):
            cromwell_harness.run_workflow(...)
    """
    return CromwellHarness(
        project_root, import_dirs, java_bin, java_args, cromwell_jar_file,
        cromwell_args
    )


@pytest.fixture(scope="function")
def workflow_runner(cromwell_harness, test_execution_dir):
    """
    Provides a callable that runs a workflow (with the same signature as
    `CromwellHarness.run_workflow`) with the execution_dir being the one
    provided by the `test_execution_dir` fixture.
    """
    def _run_workflow(wdl_script, workflow_name, inputs, expected):
        with chdir(test_execution_dir):
            cromwell_harness.run_workflow(
                wdl_script, workflow_name, inputs, expected
            )
    return _run_workflow
