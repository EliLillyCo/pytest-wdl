import os
import stat
from pathlib import Path

from pytest_cromwell.utils import (
    tempdir, chdir, test_dir as _test_dir, to_path, resolve_file,
    find_executable_path
)


def test_tempdir():
    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("foo")

    assert not foo.exists()


def test_cd():
    curdir = Path.cwd()

    with chdir("/"):
        assert Path.cwd() == Path("/")

    assert Path.cwd() == curdir


def test_test_dir():
    with tempdir() as d1:
        os.environ.setdefault("FOO", str(d1))

        with _test_dir("FOO") as d2:
            foo = d2 / "foo"
            with open(foo, "wt") as out:
                out.write("foo")

        assert foo.exists()

        with _test_dir("BAR") as d3:
            bar = d3 / "bar"
            with open(bar, "wt") as out:
                out.write("bar")

        assert not bar.exists()

        d4 = d1 / "blorf"
        assert not d4.exists()
        os.environ.setdefault("BLORF", str(d4))
        with _test_dir("BLORF"):
            assert d4.exists()

    assert not foo.exists()


def test_to_path():
    cwd = Path.cwd()
    assert to_path(cwd) == cwd
    cwd_str = str(cwd)
    assert to_path(cwd_str) == cwd
    assert to_path(cwd.name, cwd.parent) == cwd


def test_resolve_file():
    with tempdir() as d:
        assert resolve_file(d, project_root=None) == d
        f = d / "foo" / "bar"
        f.parent.mkdir(parents=True)
        with open(f, "wt") as out:
            out.write("foo")
        assert resolve_file("foo/bar", d) == f
        assert resolve_file("foo/bar", d / "foo") == f
        with chdir(d / "foo"):
            assert resolve_file("bar", project_root=d) == f


def test_find_project_path():
    pass


def test_find_executable_path():
    with tempdir() as d:
        f = d / "foo"
        with open(f, "wt") as out:
            out.write("foo")
        os.chmod(f, stat.S_IRUSR)
        assert find_executable_path("foo", [d]) is None
        _make_executable(f)
        assert find_executable_path("foo", [d]) == f


def _make_executable(f):
    current_permissions = stat.S_IMODE(os.lstat(f).st_mode)
    os.chmod(f, current_permissions | stat.S_IXUSR)
