"""
Fixtures for writing tests that execute WDL workflows using Cromwell. For testability
purposes, the implementaiton of these fixtures is done in the pytest_wdl.fixtures
module.
"""
from pytest_wdl import fixtures
import pytest


user_config_file = pytest.fixture(scope="session")(fixtures.user_config_file)
user_config = pytest.fixture(scope="session")(fixtures.user_config)
project_root_files = pytest.fixture(scope="module")(fixtures.project_root_files)
project_root = pytest.fixture(scope="module")(fixtures.project_root)
workflow_data_descriptor_file = pytest.fixture(scope="module")(fixtures.workflow_data_descriptor_file)
workflow_data_descriptors = pytest.fixture(scope="module")(fixtures.workflow_data_descriptors)
workflow_data_resolver = pytest.fixture(scope="module")(fixtures.workflow_data_resolver)
workflow_data = pytest.fixture(scope="function")(fixtures.workflow_data)
import_paths = pytest.fixture(scope="module")(fixtures.import_paths)
import_dirs = pytest.fixture(scope="module")(fixtures.import_dirs)
workflow_runner = pytest.fixture(scope="function")(fixtures.workflow_runner)
