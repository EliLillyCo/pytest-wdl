import gzip
from pytest_wdl.core import (
    LinkLocalizer, StringLocalizer, UrlLocalizer, DataFile, DataDirs, DataResolver
)
from pytest_wdl.utils import tempdir
from . import no_internet, setenv
import pytest
from unittest.mock import Mock


# TODO: switch after repo is made public
# GOOD_URL = "https://raw.githubusercontent.com/EliLillyCo/pytest-wdl/master/tests/remote_data/sample.vcf"
GOOD_URL = "https://gist.githubusercontent.com/jdidion/0f20e84187437e29d5809a78b6c4df2d/raw/d8aee6dda0f91d75858bfd35fffcf2afe3b0f45d/test_file"


def test_link_localizer():
    with tempdir() as d:
        foo = d / "foo"
        with open(foo, "wt") as out:
            out.write("foo")
        bar = d / "bar"
        localizer = LinkLocalizer(foo)
        localizer.localize(bar)
        assert bar.exists()
        assert bar.is_symlink()


def test_data_file():
    with tempdir() as d:
        foo = d / "foo.txt"
        with pytest.raises(ValueError):
            DataFile(foo, None, None)

        bar = d / "bar.txt"
        with open(foo, "wt") as out:
            out.write("foo\nbar")
        df = DataFile(bar, LinkLocalizer(foo), allowed_diff_lines=None)

        baz = d / "baz.txt"
        with open(baz, "wt") as out:
            out.write("foo\nbar")
        df.assert_contents_equal(baz)
        df.assert_contents_equal(str(baz))
        df.assert_contents_equal(DataFile(baz))

        blorf = d / "blorf.txt"
        with open(blorf, "wt") as out:
            out.write("foo\nblorf\nbork")
        with pytest.raises(AssertionError):
            df.assert_contents_equal(blorf)
        df.allowed_diff_lines = 1
        with pytest.raises(AssertionError):
            df.assert_contents_equal(blorf)
        df.allowed_diff_lines = 2
        df.assert_contents_equal(blorf)


def test_data_file_gz():
    with tempdir() as d:
        foo = d / "foo.txt.gz"
        with gzip.open(foo, "wt") as out:
            out.write("foo\nbar")
        df = DataFile(foo, allowed_diff_lines=1)

        bar = d / "bar.txt.gz"
        with gzip.open(bar, "wt") as out:
            out.write("foo\nbaz")

        df.assert_contents_equal(bar)
        df.assert_contents_equal(str(bar))
        df.assert_contents_equal(DataFile(bar))


def test_string_localizer():
    with tempdir() as d:
        foo = d / "foo"
        StringLocalizer("foo").localize(foo)
        with open(foo, "rt") as inp:
            assert inp.read() == "foo"


@pytest.mark.skipif(no_internet, reason="no internet available")
def test_url_localizer():
    good_url = GOOD_URL
    bad_url = "foo"
    with tempdir() as d:
        foo = d / "foo"
        UrlLocalizer(good_url).localize(foo)
        with open(foo, "rt") as inp:
            assert inp.read() == "foo"

    with pytest.raises(RuntimeError):
        UrlLocalizer(bad_url).localize(foo)


def test_data_dirs():
    with tempdir() as d:
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
        with pytest.raises(RuntimeError):
            DataDirs(d, mod, fun, cls)
        dd = DataDirs(d / "foo", mod, fun, cls)
        assert dd.paths == [
            mod_cls_fun,
            d / "foo" / "bar" / "baz",
            d / "foo" / "bar",
            data_mod_cls_fun,
            d / "data" / "foo" / "bar" / "baz",
            d / "data" / "foo" / "bar",
            d / "data"
        ]
        mod_cls_fun = d / "foo" / "bar" / "blorf"
        mod_cls_fun.mkdir(parents=True)
        data_mod_cls_fun = d / "data" / "foo" / "bar" / "blorf"
        data_mod_cls_fun.mkdir(parents=True)
        dd = DataDirs(d / "foo", mod, fun)
        assert dd.paths == [
            mod_cls_fun,
            d / "foo" / "bar",
            data_mod_cls_fun,
            d / "data" / "foo" / "bar",
            d / "data"
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
        resolver = DataResolver(test_data)
        with pytest.raises(ValueError):
            resolver.resolve("bork", dd)
        assert resolver.resolve("foo", dd).path == foo_txt
        assert resolver.resolve("bar", dd) == 1


def test_data_resolver_create_from_contents():
    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "path": "foo.txt",
                "contents": "foo"
            }
        }, d)
        foo = resolver.resolve("foo")
        assert foo.path == d / "foo.txt"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "name": "foo.txt",
                "contents": "foo"
            }
        }, d)
        foo = resolver.resolve("foo")
        assert foo.path == d / "foo.txt"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "contents": "foo"
            }
        }, d)
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
                "path": "sample.vcf"
            }
        }, d)
        foo = resolver.resolve("foo")
        assert foo.path == d / "sample.vcf"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "url": GOOD_URL,
                "name": "sample.vcf"
            }
        }, d)
        foo = resolver.resolve("foo")
        assert foo.path == d / "sample.vcf"
        with open(foo.path, "rt") as inp:
            assert inp.read() == "foo"

    with tempdir() as d:
        resolver = DataResolver({
            "foo": {
                "url": GOOD_URL
            }
        }, d)
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
        }, d1)
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
