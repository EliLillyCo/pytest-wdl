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
import stat
from pathlib import Path

import pytest

from pytest_wdl.utils import (
    tempdir,
    chdir,
    context_dir,
    ensure_path,
    resolve_file,
    find_executable_path,
    find_project_path,
    env_map,
    safe_string,
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


def test_ensure_path():
    cwd = Path.cwd()
    assert ensure_path(cwd) == cwd

    cwd_str = str(cwd)
    assert ensure_path(cwd_str) == cwd
    assert ensure_path(cwd.name, [cwd.parent]) == cwd

    assert ensure_path(cwd.name, [cwd.parent]) == cwd

    home = Path.home()
    assert ensure_path("~", canonicalize=False) == Path("~")
    assert ensure_path("~", canonicalize=True) == home

    with tempdir() as d:
        with pytest.raises(FileNotFoundError):
            ensure_path(d / "foo", exists=True)

        foo = d / "foo"
        assert not foo.exists()
        bar = foo / "bar"
        ensure_path(bar, is_file=True, create=True)
        assert foo.exists()

        with open(bar, "wt") as out:
            out.write("foo")
        ensure_path(bar, exists=True, is_file=True)
        with pytest.raises(NotADirectoryError):
            ensure_path(bar, exists=True, is_file=False)
        with pytest.raises(OSError):
            ensure_path(bar, exists=True, is_file=True, executable=True)
        os.chmod(bar, bar.stat().st_mode | stat.S_IEXEC)
        ensure_path(bar, exists=True, is_file=True, executable=True)

        baz = d / "baz"
        assert not baz.exists()
        ensure_path(baz, is_file=False, create=True)
        assert baz.exists()
        assert baz.is_dir()

        with pytest.raises(FileExistsError):
            ensure_path(baz, exists=False)

        with pytest.raises(IsADirectoryError):
            ensure_path(baz, exists=True, is_file=True)


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
    with tempdir(change_dir=True) as d:
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
    with setenv(
        {"FOOVAR1": "http://foo.com",}
    ):
        assert env_map({"http": "FOOVAR1", "https": "FOOVAR2"}) == {
            "http": "http://foo.com"
        }


def test_safe_string():
    assert safe_string("a+b*c") == "a_b_c"
