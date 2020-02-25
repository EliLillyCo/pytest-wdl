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
Fixtures for writing tests that execute WDL workflows using Cromwell. For testability
purposes, the implementaiton of these fixtures is done in the pytest_wdl.fixtures
module.
"""
from pytest_wdl import fixtures
from pytest_wdl.executors import ExecutionFailedError
from pytest_wdl.loader import pytest_collection, pytest_collect_file

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
default_executors = pytest.fixture(scope="session")(fixtures.default_executors)
workflow_runner = pytest.fixture(scope="function")(fixtures.workflow_runner)
