import os
import stat
from pathlib import Path

import pytest
from pytest_wdl.utils import (
    tempdir, chdir, context_dir, ensure_path, resolve_file,
    find_executable_path, find_project_path, env_map
)
from . import setenv, make_executable


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


def test_context_dir():
    with tempdir() as d1:
        with context_dir(d1 / "foo") as d2:
            foo = d2 / "foo"
            with open(foo, "wt") as out:
                out.write("foo")

        assert foo.exists()

        with context_dir() as d3:
            bar = d3 / "bar"
            with open(bar, "wt") as out:
                out.write("bar")

        assert not bar.exists()

        d4 = d1 / "blorf"
        assert not d4.exists()
        with context_dir(d4):
            assert d4.exists()
        with context_dir(d4, cleanup=True):
            pass
        assert not d4.exists()

    assert not foo.exists()


def test_to_path():
    cwd = Path.cwd()
    assert ensure_path(cwd) == cwd
    cwd_str = str(cwd)
    assert ensure_path(cwd_str) == cwd
    assert ensure_path(cwd.name, cwd.parent) == cwd


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


def test_resolve_missing_file():
    with tempdir() as d:
        assert resolve_file("foo", project_root=d, assert_exists=False) is None
        with pytest.raises(FileNotFoundError):
            resolve_file("foo", project_root=d, assert_exists=True)


def test_find_project_path():
    with tempdir() as d:
        with pytest.raises(FileNotFoundError):
            assert find_project_path("foo", start=d, assert_exists=True)
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("foo")
        assert find_project_path("foo", start=d, return_parent=False) == foo
        assert find_project_path("foo", start=d, return_parent=True) == d


def test_find_executable_path():
    with tempdir() as d:
        f = d / "foo"
        with open(f, "wt") as out:
            out.write("foo")
        os.chmod(f, stat.S_IRUSR)
        assert find_executable_path("foo", [d]) is None
        make_executable(f)
        assert find_executable_path("foo", [d]) == f


def test_find_executable_path_system():
    with tempdir() as d:
        f = d / "foo"
        with open(f, "wt") as out:
            out.write("foo")
        os.chmod(f, stat.S_IRUSR)
        with setenv({"PATH": str(d)}):
            assert find_executable_path("foo") is None
            make_executable(f)
            assert find_executable_path("foo") == f


def test_env_map():
    with setenv({
        "FOOVAR1": "http://foo.com",
    }):
        assert env_map({
            "http": "FOOVAR1",
            "https": "FOOVAR2"
        }) == {
            "http": "http://foo.com"
        }
