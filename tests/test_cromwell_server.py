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

import os
import time

import subby
import pytest

from pytest_wdl.executors import ENV_JAVA_HOME
from pytest_wdl.executors.cromwell_local import ENV_CROMWELL_JAR


@pytest.mark.integration
@pytest.mark.remote
def test_cromwell_server_workflow(user_config, workflow_data, workflow_runner):
    cromwell_jar_file = user_config.get_executor_defaults("cromwell").get(
        "cromwell_jar_file", os.environ.get(ENV_CROMWELL_JAR)
    )

    java_jar = user_config.get_executor_defaults("cromwell").get(
        "java_bin", os.environ.get(ENV_JAVA_HOME) + "/bin/java"
    )

    p = subby.run(
        f"{java_jar} -jar {cromwell_jar_file} server | tee /dev/stderr", block=False
    )
    time.sleep(10)
    inputs = {
        "in_txt": workflow_data["in_txt"],
        "in_int": 1
    }
    outputs = {
        "out_txt": workflow_data["out_txt"],
        "out_int": 1
    }

    try:
        workflow_runner(
            "test.wdl",
            inputs,
            outputs,
            executors=["cromwell-server"]
        )
    finally:
        p.kill()
