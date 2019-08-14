"""
Fixtures for writing tests that execute WDL workflows using Cromwell. For testability
purposes, the implementaiton of these fixtures is done in the pytest_wdl.fixtures
module.
"""
from pytest_wdl import fixtures
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--wdl-config", default=None,
        help="Path to JSON file with environment-specifc configuration."
    )


wdl_config_file = pytest.fixture(scope="session")(fixtures.wdl_config_file)
project_root_files = pytest.fixture(scope="module")(fixtures.project_root_files)
project_root = pytest.fixture(scope="module")(fixtures.project_root)
workflow_data_descriptor_file = pytest.fixture(scope="module")(fixtures.workflow_data_descriptor_file)
workflow_data_descriptors = pytest.fixture(scope="module")(fixtures.workflow_data_descriptors)
workflow_data_resolver = pytest.fixture(scope="module")(fixtures.workflow_data_resolver)
workflow_data = pytest.fixture(scope="function")(fixtures.workflow_data)
import_paths = pytest.fixture(scope="module")(fixtures.import_paths)
import_dirs = pytest.fixture(scope="module")(fixtures.import_dirs)
cromwell_config = pytest.fixture(scope="session")(fixtures.cromwell_config)
cromwell_harness = pytest.fixture(scope="module")(fixtures.cromwell_harness)
workflow_runner = pytest.fixture(scope="function")(fixtures.workflow_runner)
