import contextlib
import os
from pathlib import Path
import stat


@contextlib.contextmanager
def setenv(envvars: dict):
    cur_values = {}
    to_remove = []
    for k, v in envvars.items():
        if k not in os.environ:
            to_remove.append(k)
        else:
            cur_values[k] = os.environ[k]
            if v is None:
                del os.environ[k]
            else:
                os.environ[k] = v
    try:
        yield
    finally:
        os.environ.update(cur_values)
        for k in to_remove:
            del os.environ[k]


def make_executable(path: Path):
    current_permissions = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, current_permissions | stat.S_IXUSR)
