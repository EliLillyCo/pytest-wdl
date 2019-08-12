"""
Fixtures for writing tests that execute WDL workflows using Cromwell. For testability
purposes, the implementaiton of these fixtures is done in the pytest_wdl.fixtures
module.
"""
from pytest_wdl import fixtures
import pytest


project_root_files = pytest.fixture(scope="module")(fixtures.project_root_files)
project_root = pytest.fixture(scope="module")(fixtures.project_root)
workflow_data_descriptor_file = pytest.fixture(scope="module")(fixtures.workflow_data_descriptor_file)
workflow_data_descriptors = pytest.fixture(scope="module")(fixtures.workflow_data_descriptors)
cache_dir = pytest.fixture(scope="module")(fixtures.cache_dir)
execution_dir = pytest.fixture(scope="function")(fixtures.execution_dir)
proxy_map = pytest.fixture(scope="session")(fixtures.proxy_map)
proxies = pytest.fixture(scope="session")(fixtures.proxies)
import_paths = pytest.fixture(scope="module")(fixtures.import_paths)
import_dirs = pytest.fixture(scope="module")(fixtures.import_dirs)
java_bin = pytest.fixture(scope="session")(fixtures.java_bin)
cromwell_config_file = pytest.fixture(scope="session")(fixtures.cromwell_config_file)
java_args = pytest.fixture(scope="session")(fixtures.java_args)
cromwell_jar_file = pytest.fixture(scope="session")(fixtures.cromwell_jar_file)
cromwell_args = pytest.fixture(scope="session")(fixtures.cromwell_args)
workflow_data_resolver = pytest.fixture(scope="module")(fixtures.workflow_data_resolver)
workflow_data = pytest.fixture(scope="function")(fixtures.workflow_data)
cromwell_harness = pytest.fixture(scope="module")(fixtures.cromwell_harness)
workflow_runner = pytest.fixture(scope="function")(fixtures.workflow_runner)
