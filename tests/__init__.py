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

import contextlib
import os
import socket
from pathlib import Path
import stat
from unittest.mock import Mock

# Change URLs once foo.txt is pushed to master
#GOOD_URL = "https://raw.githubusercontent.com/EliLillyCo/pytest-wdl/master/tests/remote_data/foo.txt"
GOOD_URL = "https://gist.githubusercontent.com/jdidion/0f20e84187437e29d5809a78b6c4df2d/raw/d8aee6dda0f91d75858bfd35fffcf2afe3b0f45d/test_file"


try:
    # TODO: is there a better method for testing whether
    #  internet access is available?
    socket.create_connection(("www.google.com", 80))
    no_internet = False
except OSError:
    no_internet = True


@contextlib.contextmanager
def setenv(envvars: dict):
    cur_values = {}
    to_remove = []
    for k, v in envvars.items():
        if k in os.environ:
            cur_values[k] = os.environ[k]
            if v is None:
                os.environ.pop(k)
            else:
                os.environ[k] = str(v)
        elif v is not None:
            to_remove.append(k)
            os.environ[k] = str(v)
    try:
        yield
    finally:
        os.environ.update(cur_values)
        for k in to_remove:
            os.environ.pop(k)


def make_executable(path: Path):
    current_permissions = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, current_permissions | stat.S_IXUSR)


def mock_request(dirpath: Path):
    fspath = Mock()
    fspath.dirpath = lambda: dirpath
    req = Mock()
    req.fspath = fspath
    return req
