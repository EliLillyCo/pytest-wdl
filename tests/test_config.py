import json
import re

from pytest_wdl.config import UserConfiguration
from pytest_wdl.utils import tempdir
from . import setenv


def test_user_config_no_defaults():
    with tempdir(True):
        config = UserConfiguration()
        assert config.remove_cache_dir is True
        assert config.cache_dir.exists()
        config.cleanup()
        assert not config.cache_dir.exists()


def test_user_config_from_file():
    with tempdir() as d, setenv({
        "HTTPS_PROXY": "http://foo.com/https",
        "FOO_HEADER": "bar"
    }):
        cache_dir = d / "cache"
        execution_dir = d / "execution"
        config_dict = {
            "cache_dir": str(cache_dir),
            "execution_dir": str(execution_dir),
            "proxies": {
                "http": {
                    "value": "http://foo.com/http"
                },
                "https": {
                    "env": "HTTPS_PROXY"
                }
            },
            "http_headers": [
                {
                    "pattern": "http://foo.com/.*",
                    "name": "foo",
                    "env": "FOO_HEADER"
                }
            ],
            "executors": {
                "foo": {
                    "bar": 1
                }
            }
        }
        config_file = d / "config.json"
        with open(config_file, "wt") as out:
            json.dump(config_dict, out)
        config = UserConfiguration(config_file)
        assert config.cache_dir == cache_dir
        assert config.default_execution_dir == execution_dir
        assert config.proxies == {
            "http": "http://foo.com/http",
            "https": "http://foo.com/https"
        }
        assert config.default_http_headers == [
            {
                "pattern": re.compile("http://foo.com/.*"),
                "name": "foo",
                "env": "FOO_HEADER"
            }
        ]
        assert config.get_executor_defaults("foo") == {"bar": 1}
