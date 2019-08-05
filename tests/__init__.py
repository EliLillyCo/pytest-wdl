import contextlib
import os
from pathlib import Path
import stat
import urllib.request


try:
    # TODO: is there a better method for testing whether
    #  internet access is available?
    urllib.request.urlopen("http://google.com")
    no_internet = False
except:
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
                os.environ[k] = v
        elif v is not None:
            to_remove.append(k)
            os.environ[k] = v
    try:
        yield
    finally:
        os.environ.update(cur_values)
        for k in to_remove:
            os.environ.pop(k)


def make_executable(path: Path):
    current_permissions = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, current_permissions | stat.S_IXUSR)
