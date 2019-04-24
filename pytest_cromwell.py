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
import json
import logging
import os
import importlib.util

import pytest

from pytest_cromwell_core.utils import DataFile, _test_dir, tempdir, chdir, \
    CromwellHarness

LOG = logging.getLogger("pytest-cromwell")
LOG.setLevel(os.environ.get("LOGLEVEL", "WARNING").upper())


def _deprecated(f):
    """
    Decorator for deprecated functions/methods. Deprecated functionality will be
    removed before each major release.
    """
    def decorator(*args, **kwargs):
        LOG.warning(f"Function/method {f.__name__} is deprecated and will be removed")
        f(*args, **kwargs)
    return decorator


def load_data_type_plugin(data_type):
    """
    Load the module for the Data Type plugin that is specified in the test
    data attributes. This expects a module to exist in the package
    pytest_cromwell_plugins.data_types.

    :param data_type: desired data type, should match the module name in
      pytest_cromwell_plugs.data_types
    """
    data_types_dir = os.path.join(
        os.path.dirname(__file__), 'pytest_cromwell_plugins/data_types'
    )
    mod_abs_path = os.path.join(data_types_dir, data_type + '.py')
    if not os.path.exists(mod_abs_path):
        raise FileNotFoundError(
            f"You specified a plugin data type of {data_type}, which does "
            f"not exist. Consider fixing this type definition, removing "
            f"it, or adding a new plugin for this type."
        )
    spec = importlib.util.spec_from_file_location(data_type, mod_abs_path)
    data_type_plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data_type_plugin)


def update_available_data_types():
    """
    Check which subclasses of DataFile have been imported and return the
    new dictionary. This expects the subclass to have an attribute of 'name'
    that can be used to set the key.
    """
    data_types = {cls.name: cls for cls in DataFile.__subclasses__()}
    data_types['default'] = DataFile
    return data_types


class Data:
    """
    Class that manages test data.

    Args:
        data_dir: Directory where test data files should be stored temporarily, if
            they are being downloaded from a remote server.
        data_file: JSON file describing the test data.
        http_headers: Http(s) headers.
        proxies: Http(s) proxies.
    """
    def __init__(self, data_dir, data_file, http_headers, proxies):
        self.data_dir = data_dir
        self.http_headers = http_headers
        self.proxies = proxies
        self._values = {}
        with open(data_file, "rt") as inp:
            self._data = json.load(inp)

    def __getitem__(self, name):
        if name not in self._values:
            if name not in self._data:
                raise ValueError(f"Unrecognized name {name}")
            value = self._data[name]
            if isinstance(value, dict):
                # update available data_types
                if 'type' in value:
                    desired_type = value.get('type')
                    if desired_type != 'default':
                        load_data_type_plugin(desired_type)
                data_types = update_available_data_types()
                data_file_class = data_types[value.pop("type", "default")]
                self._values[name] = data_file_class(
                    local_dir=self.data_dir, http_headers=self.http_headers,
                    proxies=self.proxies, **value
                )
            else:
                self._values[name] = value

        return self._values[name]


@pytest.fixture(scope="module")
def project_root(request):
    """
    Fixture that provides the root directory of the project. By default, this
    assumes that the project has one subdirectory per task, and that this
    framework is being run from the test subdirectory of a task diretory, and
    therefore looks for the project root two directories up.
    """
    return os.path.abspath(os.path.join(os.path.dirname(request.fspath), "../.."))


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
    with _test_dir("TEST_DATA_DIR", project_root) as data_dir:
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
    with _test_dir("TEST_EXECUTION_DIR", project_root) as execution_dir:
        yield execution_dir


@pytest.fixture(scope="session")
@_deprecated
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
def test_data(test_data_file, test_data_dir, http_headers, proxies):
    """
    Provides an accessor for test data files, which may be local or in a remote
    repository. Requires a `test_data_file` argument, which is provided by a
    `@pytest.mark.parametrize` decoration. The test_data_file file is a JSON file
    with keys being workflow input or output parametrize, and values being hashes with
    any of the following keys:

    * url: URL to the remote data file
    * path: Path to the local data file
    * type: File type; recoginzed values: "vcf"

    Args:
        test_data_file: test_data_file fixture.
        test_data_dir: test_data_dir fixture.
        http_headers: http_headers fixture.
        proxies: proxies fixture.

    Examples:
        @pytest.fixture(scope="session")
        def test_data_file():
            return "tests/test_data.json"

        def test_workflow(test_data):
            print(test_data["myfile"])
    """
    return Data(test_data_dir, test_data_file, http_headers, proxies)


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
