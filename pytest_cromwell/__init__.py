"""
Fixtures for writing tests that execute WDL workflows using Cromwell. For testability
purposes, the implementaiton of these fixtures is done in the pytest_cromwell.fixtures
module.
"""
from pytest_cromwell import fixtures
import pytest


project_root_files = pytest.fixture(scope="module")(fixtures.project_root_files)
project_root = pytest.fixture(scope="module")(fixtures.project_root)
test_data_file = pytest.fixture(scope="module")(fixtures.test_data_file)
test_data_dir = pytest.fixture(scope="module")(fixtures.test_data_dir)
test_execution_dir = pytest.fixture(scope="function")(fixtures.test_execution_dir)
http_header_map = pytest.fixture(scope="session")(fixtures.http_header_map)
http_headers = pytest.fixture(scope="session")(fixtures.http_headers)
proxy_map = pytest.fixture(scope="session")(fixtures.proxy_map)
proxies = pytest.fixture(scope="session")(fixtures.proxies)
import_paths = pytest.fixture(scope="module")(fixtures.import_paths)
import_dirs = pytest.fixture(scope="module")(fixtures.import_dirs)
java_bin = pytest.fixture(scope="session")(fixtures.java_bin)
cromwell_config_file = pytest.fixture(scope="session")(fixtures.cromwell_config_file)
java_args = pytest.fixture(scope="session")(fixtures.java_args)
cromwell_jar_file = pytest.fixture(scope="session")(fixtures.cromwell_jar_file)
cromwell_args = pytest.fixture(scope="session")(fixtures.cromwell_args)
test_data_resolver = pytest.fixture(scope="module")(fixtures.test_data_resolver)
test_data = pytest.fixture(scope="function")(fixtures.test_data)
cromwell_harness = pytest.fixture(scope="module")(fixtures.cromwell_harness)
workflow_runner = pytest.fixture(scope="function")(fixtures.workflow_runner)
