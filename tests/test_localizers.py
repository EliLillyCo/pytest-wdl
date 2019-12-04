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
import json
import re
import pytest
from pytest_wdl.config import UserConfiguration
from pytest_wdl.localizers import (
    LinkLocalizer, StringLocalizer, JsonLocalizer, UrlLocalizer
)
from pytest_wdl.utils import DigestsNotEqualError, tempdir
from . import GOOD_URL, no_internet, setenv


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


def test_string_localizer():
    with tempdir() as d:
        foo = d / "foo"
        StringLocalizer("foo").localize(foo)
        with open(foo, "rt") as inp:
            assert inp.read() == "foo"


def test_json_localizer():
    with tempdir() as d:
        foo = d / "foo"
        contents = {
            "foo": 1,
            "bar": "a"
        }
        JsonLocalizer(contents).localize(foo)
        with open(foo, "rt") as inp:
            assert json.load(inp) == contents


@pytest.mark.skipif(no_internet, reason="no internet available")
def test_url_localizer():
    good_url = GOOD_URL
    bad_url = "foo"
    with tempdir() as d:
        foo = d / "foo"
        UrlLocalizer(
            good_url,
            UserConfiguration(None, cache_dir=d),
            digests={"md5": "acbd18db4cc2f85cedef654fccc4a4d8"}
        ).localize(foo)
        with open(foo, "rt") as inp:
            assert inp.read() == "foo"

        # test that the file is overwritten
        with open(foo, "wt") as out:
            out.write("bork")
        UrlLocalizer(good_url, UserConfiguration(None, cache_dir=d)).localize(foo)
        with open(foo, "rt") as inp:
            assert inp.read() == "foo"

    with pytest.raises(RuntimeError):
        with tempdir() as d:
            foo = d / "foo"
            UrlLocalizer(
                good_url,
                UserConfiguration(None, cache_dir=d),
                digests={"md5": "XXX"}
            ).localize(foo)

    with pytest.raises(RuntimeError):
        UrlLocalizer(bad_url, UserConfiguration(None, cache_dir=d)).localize(foo)


# @pytest.mark.skipif(no_internet, reason="no internet available")
# def test_url_localizer_corrupt_file():
#     good_url = GOOD_URL
#     with tempdir() as d:
#         foo = d / "foo"
#         # The localizer should detect that the file already exists, but that the
#         # digests don't match and overwrite it
#         with open(foo, "wt") as out:
#             out.write("blahblahblah")
#         UrlLocalizer(
#             good_url,
#             UserConfiguration(None, cache_dir=d),
#             digests={"md5": "acbd18db4cc2f85cedef654fccc4a4d8"}
#         ).localize(foo)
#         with open(foo, "rt") as inp:
#             assert inp.read() == "foo"


def test_url_localizer_add_headers():
    with setenv({
       "FOO": "bar"
    }):
        localizer = UrlLocalizer(
            "http://foo.com/bork",
            UserConfiguration(http_headers=[
                {
                    "name": "beep",
                    "pattern": re.compile(r"http://foo.com/.*"),
                    "env": "FOO",
                    "value": "baz"
                },
                {
                    "name": "boop",
                    "pattern": re.compile(r"http://foo.*/bork"),
                    "env": "BAR",
                    "value": "blorf"
                }
            ]),
            {
                "boop": {
                    "value": "blammo"
                }
            }
        )
        headers = localizer.http_headers
        assert len(headers) == 2
        assert set(headers.keys()) == {"beep", "boop"}
        assert headers["beep"] == "bar"
        assert headers["boop"] == "blammo"


def test_url_localizer_set_proxies():
    localizer = UrlLocalizer("http://foo.com", UserConfiguration(proxies={
        "https": "https://foo.com/proxy"
    }))
    proxies = localizer.proxies
    assert len(proxies) == 1
    assert "https" in proxies
    assert proxies["https"] == "https://foo.com/proxy"
