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

import gzip
import json
from typing import cast
from unittest.mock import Mock

import pytest

from pytest_wdl.config import UserConfiguration
from pytest_wdl.core import (
    DefaultDataFile, DataDirs, DataManager, DataResolver, create_data_file
)
from pytest_wdl.localizers import LinkLocalizer, UrlLocalizer
from pytest_wdl.utils import tempdir
from . import GOOD_URL, setenv


def test_data_file():
    with tempdir() as d:
        foo = d / "foo.txt"
        with pytest.raises(ValueError):
            DefaultDataFile(foo, None)

        bar = d / "bar.txt"
        with open(foo, "wt") as out:
            out.write("foo\nbar")
        df = DefaultDataFile(bar, LinkLocalizer(foo))
        assert str(df) == str(bar)

        baz = d / "baz.txt"
        with open(baz, "wt") as out:
            out.write("foo\nbar")
        df.assert_contents_equal(baz)
        df.assert_contents_equal(str(baz))
        df.assert_contents_equal(DefaultDataFile(baz))

        blorf = d / "blorf.txt"
        with open(blorf, "wt") as out:
            out.write("foo\nblorf\nbork")
        with pytest.raises(AssertionError):
            df.assert_contents_equal(blorf)
        df.compare_opts["allowed_diff_lines"] = 1
        with pytest.raises(AssertionError):
            df.assert_contents_equal(blorf)
        df.compare_opts["allowed_diff_lines"] = 2
        df.assert_contents_equal(blorf)


def test_data_file_gz():
    with tempdir() as d:
        foo = d / "foo.txt.gz"
        with gzip.open(foo, "wt") as out:
            out.write("foo\nbar")
        df = DefaultDataFile(foo, allowed_diff_lines=0)

        # Compare identical files
        bar = d / "bar.txt.gz"
        with gzip.open(bar, "wt") as out:
            out.write("foo\nbar")
        df.assert_contents_equal(bar)
        df.assert_contents_equal(str(bar))
        df.assert_contents_equal(DefaultDataFile(bar))

        # Compare differing files
        df.set_compare_opts(allowed_diff_lines=1)
        baz = d / "baz.txt.gz"
        with gzip.open(baz, "wt") as out:
            out.write("foo\nbaz")
        df.assert_contents_equal(bar)
        df.assert_contents_equal(str(bar))
        df.assert_contents_equal(DefaultDataFile(bar))


def test_data_file_dict_type():
    with tempdir() as d:
        foo = d / "foo.txt.gz"
        with gzip.open(foo, "wt") as out:
            out.write("foo\nbar")
        df = create_data_file(
            user_config=UserConfiguration(),
            path=foo,
            type={
                "name": "default",
                "allowed_diff_lines": 1
            }
        )

        bar = d / "bar.txt.gz"
        with gzip.open(bar, "wt") as out:
            out.write("foo\nbaz")

        df.assert_contents_equal(bar)
        df.assert_contents_equal(str(bar))
        df.assert_contents_equal(DefaultDataFile(bar))


def test_data_file_class():
    dd = DataResolver(data_descriptors={
        "foo": {
            "class": "bar",
            "value": 1
        }
    }, user_config=UserConfiguration())
    assert dd.resolve("foo") == 1


def test_data_file_json_contents():
    with tempdir() as d:
        foo = d / "foo.json"
        df = create_data_file(
            user_config=UserConfiguration(),
            path=foo,
            contents={
                "a": 1,
                "b": "foo"
            }
        )
        with open(df.path, "rt") as inp:
            assert json.load(inp) == {
                "a": 1,
                "b": "foo"
            }


def test_data_dirs():
    with tempdir() as d:
        mod = Mock()
        mod.__name__ = "tests.bar"
        cls = Mock()
        cls.__name__ = "baz"
        fun = Mock()
        fun.__name__ = "blorf"
        mod_cls_fun = d / "tests" / "bar" / "baz" / "blorf"
        mod_cls_fun.mkdir(parents=True)
        data_mod_cls_fun = d / "tests" / "data" / "bar" / "baz" / "blorf"
        data_mod_cls_fun.mkdir(parents=True)

        dd = DataDirs(d / "tests", mod, fun, cls)
        assert dd.paths == [
            mod_cls_fun,
            d / "tests" / "bar" / "baz",
            d / "tests" / "bar",
            data_mod_cls_fun,
            d / "tests" / "data" / "bar" / "baz",
            d / "tests" / "data" / "bar",
            d / "tests" / "data"
        ]

        mod_cls_fun = d / "tests" / "bar" / "blorf"
        mod_cls_fun.mkdir(parents=True)
        data_mod_cls_fun = d / "tests" / "data" / "bar" / "blorf"
        data_mod_cls_fun.mkdir(parents=True)
        dd = DataDirs(d / "tests", mod, fun)
        assert dd.paths == [
            mod_cls_fun,
            d / "tests" / "bar",
            data_mod_cls_fun,
            d / "tests" / "data" / "bar",
            d / "tests" / "data"
        ]


def test_data_resolver():
    with tempdir() as d:
        test_data = {
            "foo": {
                "name": "foo.txt"
            },
            "bar": 1
        }
        foo_txt = d / "data" / "foo.txt"
        foo_txt.parent.mkdir()
        with open(foo_txt, "wt") as out:
            out.write("bar")
        mod = Mock()
        mod.__name__ = ""
        fun = Mock()
        fun.__name__ = "test_foo"
        dd = DataDirs(d, mod, fun)
        resolver = DataResolver(test_data, UserConfiguration(None, cache_dir=d))
        with pytest.raises(FileNotFoundError):
            resolver.resolve("bork", dd)
        assert resolver.resolve("foo", dd).path == foo_txt
        assert resolver.resolve("bar", dd) == 1


def test_data_resolver_env():
    with tempdir() as d:
        path = d / "foo.txt"
        with open(path, "wt") as out:
            out.write("foo")
        with setenv({"FOO": str(path)}):
            resolver = DataResolver({
                "foo": {
                    "env": "FOO"
                }
            }, UserConfiguration(None, cache_dir=d))
            assert resolver.resolve("foo").path == path

            bar = d / "bar.txt"
            resolver = DataResolver({
                "foo": {
                    "env": "FOO",
                    "path": bar
                }
            }, UserConfiguration(None, cache_dir=d))
            assert resolver.resolve("foo").path == bar


def test_data_resolver_local_path():
    with tempdir() as d:
        path = d / "foo.txt"
        with open(path, "wt") as out:
            out.write("foo")
        resolver = DataResolver({
            "foo": {
                "path": "foo.txt"
            }
        }, UserConfiguration(None, cache_dir=d))
        assert resolver.resolve("foo").path == path

        with setenv({"MYPATH": str(d)}):
            resolver = DataResolver({
                "foo": {
                    "path": "${MYPATH}/foo.txt"
                }
            }, UserConfiguration(None, cache_dir=d))
            assert resolver.resolve("foo").path == path


def test_data_resolver_create_from_contents():
    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "path": "dir1/dir2/foo.txt",
                "contents": "foo"
            }
        }, UserConfiguration(None, cache_dir=d))
        parent = d / "dir1" / "dir2"
        foo = resolver.resolve("foo")
        assert foo.path == parent / "foo.txt"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "name": "foo.txt",
                "contents": "foo"
            }
        }, UserConfiguration(None, cache_dir=d))
        foo = resolver.resolve("foo")
        assert foo.path == d / "foo.txt"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "contents": "foo"
            }
        }, UserConfiguration(None, cache_dir=d))
        foo = resolver.resolve("foo")
        assert foo.path.parent == d
        assert foo.path.exists()
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"


def test_data_resolver_create_from_url():
    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "url": GOOD_URL,
                "path": "dir1/dir2/sample.vcf"
            }
        }, UserConfiguration(None, cache_dir=d))
        foo = resolver.resolve("foo")
        assert foo.path == d / "dir1" / "dir2" / "sample.vcf"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "url": GOOD_URL,
                "name": "sample.vcf"
            }
        }, UserConfiguration(None, cache_dir=d))
        foo = resolver.resolve("foo")
        assert foo.path == d / "sample.vcf"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "url": GOOD_URL
            }
        }, UserConfiguration(None, cache_dir=d))
        foo = resolver.resolve("foo")
        assert foo.path == d / "test_file"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"


def test_data_resolver_create_from_datadir():
    with tempdir() as d, tempdir() as d1:
        mod = Mock()
        mod.__name__ = "foo.bar"
        cls = Mock()
        cls.__name__ = "baz"
        fun = Mock()
        fun.__name__ = "blorf"
        mod_cls_fun = d / "foo" / "bar" / "baz" / "blorf"
        mod_cls_fun.mkdir(parents=True)
        data_mod_cls_fun = d / "data" / "foo" / "bar" / "baz" / "blorf"
        data_mod_cls_fun.mkdir(parents=True)
        dd = DataDirs(d / "foo", mod, fun, cls)

        resolver = DataResolver({
            "boink": {
                "name": "boink.txt",
            },
            "bobble": {
                "name": "bobble.txt"
            },
            "burp": {
                "name": "burp.txt",
                "path": "burp.txt"
            }
        }, UserConfiguration(None, cache_dir=d1))
        boink = d / "foo" / "bar" / "boink.txt"
        with open(boink, "wt") as out:
            out.write("boink")
        assert boink == resolver.resolve("boink", dd).path

        with pytest.raises(FileNotFoundError):
            resolver.resolve("bobble", dd)

        burp = d / "foo" / "bar" / "burp.txt"
        with open(burp, "wt") as out:
            out.write("burp")
        burp_resolved = resolver.resolve("burp", dd).path
        assert burp_resolved == d1 / "burp.txt"
        assert burp_resolved.is_symlink()

        with pytest.raises(FileNotFoundError):
            resolver.resolve("bobble")


def test_data_manager():
    dm = DataManager(
        data_resolver=DataResolver(
            {
                "foo": {
                    "class": "x",
                    "value": 1
                },
                "bar": {
                    "class": "x",
                    "value": 2
                }
            }, UserConfiguration()
        ),
        datadirs=None
    )
    assert [1, 2] == dm.get_list("foo", "bar")
    assert {"foo": 1, "bork": 2} == dm.get_dict("foo", bork="bar")


def test_http_header_set_in_workflow_data():
    """
    Test that workflow data file can define the HTTP Headers. This is
    important because the URLs referenced can be from different hosts and
    require different headers, so setting them at this level allows that
    fine-grained control.
    """
    with tempdir() as d:
        config = UserConfiguration(cache_dir=d)
        assert not config.default_http_headers
        resolver = DataResolver({
            "foo": {
                "url": GOOD_URL,
                "path": "sample.vcf",
                "http_headers": {
                    "Auth-Header-Token": "TOKEN"
                }
            }
        }, config)
        foo = resolver.resolve("foo")
        assert foo.path == d / "sample.vcf"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with setenv({"TOKEN": "this_is_the_token"}), tempdir() as d:
        config = UserConfiguration(cache_dir=d)
        assert not config.default_http_headers
        resolver = DataResolver({
            "foo": {
                "url": GOOD_URL,
                "path": "sample.vcf",
                "http_headers": {
                    "Auth-Header-Token": "TOKEN"
                }
            }
        },  config)
        foo = resolver.resolve("foo")
        assert foo.path == d / "sample.vcf"
        assert isinstance(foo.localizer, UrlLocalizer)
        assert cast(UrlLocalizer, foo.localizer).http_headers == {
            "Auth-Header-Token": "this_is_the_token"
        }
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"
