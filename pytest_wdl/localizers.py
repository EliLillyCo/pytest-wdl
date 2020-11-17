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
from abc import ABCMeta, abstractmethod
import json
from pathlib import Path
from typing import Optional, cast
from urllib import request

from xphyle import open_

from pytest_wdl.config import UserConfiguration
from pytest_wdl.url_schemes import Response, ResponseWrapper
from pytest_wdl.utils import (
    LOG, DigestsNotEqualError, env_map, resolve_value_descriptor, verify_digests
)


class Localizer(metaclass=ABCMeta):  # pragma: no-cover
    """
    Abstract base of classes that implement file localization.
    """
    @abstractmethod
    def localize(self, destination: Path) -> None:
        """
        Localize a resource to `destination`.

        Args:
            destination: Path to file where the non-local resource is to be localized.
        """

    def verify(self, path: Path) -> bool:
        """Verify that `path` exists and is valid.

        Args:
            path: Path to verify.

        Returns:
            True if the path is verified, else False
        """
        return path.exists()


class UrlLocalizer(Localizer):
    """
    Localizes a file specified by a URL.
    """
    def __init__(
        self,
        url: str,
        user_config: UserConfiguration,
        http_headers: Optional[dict] = None,
        digests: Optional[dict] = None
    ):
        self.url = url
        self.user_config = user_config
        self._http_headers = http_headers
        self.digests = digests

    def verify(self, path: Path) -> bool:
        if not super().verify(path):
            return False
        if self.digests:
            try:
                verify_digests(path, self.digests)
            except DigestsNotEqualError:
                LOG.exception(
                    "%s already exists but its digest does not match the expected "
                    "digest; deleting the existing file and re-downloading from "
                    "%s", str(path), self.url
                )
                path.unlink()
                return False
        return True

    def localize(self, destination: Path):
        try:
            download_file(
                self.url,
                destination,
                http_headers=self.http_headers,
                proxies=self.user_config.proxies,
                show_progress=self.user_config.show_progress,
                digests=self.digests
            )
        except Exception as err:
            # Delete the destination since it might be incomplete
            if destination.exists():
                try:
                    destination.unlink()
                except IOError:  # TODO: test this
                    LOG.exception(
                        "Error deleting file %s; localization failed, so it may be "
                        "incomplete", str(destination)
                    )
            raise RuntimeError(f"Error localizing url {self.url}") from err

    @property
    def http_headers(self) -> dict:
        http_headers = {}

        if self._http_headers:
            http_headers.update(env_map(self._http_headers))

        if self.user_config.default_http_headers:
            for value_dict in self.user_config.default_http_headers:
                name = value_dict["name"]
                pattern = value_dict.get("pattern")
                if name not in http_headers and (
                    pattern is None or pattern.match(self.url)
                ):
                    value = resolve_value_descriptor(value_dict)
                    if value:
                        http_headers[name] = value

        return http_headers

    @property
    def proxies(self) -> dict:
        return self.user_config.proxies


class StringLocalizer(Localizer):
    """
    Localizes a string by writing it to a file.
    """
    def __init__(self, contents: str):
        self.contents = contents

    def localize(self, destination: Path):
        LOG.debug(f"Persisting {destination} from contents")
        with open_(destination, "wt") as out:
            out.write(self.contents)


class JsonLocalizer(Localizer):
    def __init__(self, contents: dict):
        self.contents = contents

    def localize(self, destination: Path):
        LOG.debug(f"Persisting {destination} from contents")
        with open(destination, "wt") as out:
            json.dump(self.contents, out)


class LinkLocalizer(Localizer):
    """
    Localizes a file to another destination using a symlink.
    """
    def __init__(self, source: Path):
        self.source = source

    def localize(self, destination: Path):
        destination.symlink_to(self.source)


def download_file(
    url: str,
    destination: Path,
    http_headers: Optional[dict] = None,
    proxies: Optional[dict] = None,
    show_progress: bool = True,
    digests: Optional[dict] = None
):
    req = request.Request(url)
    if http_headers:
        for name, value in http_headers.items():
            req.add_unredirected_header(name, value)
    if proxies:
        # TODO: Should we only set the proxy associated with the URL scheme?
        #  Should we raise an exception if there is not a proxy defined for
        #  the URL scheme?
        # parsed = parse.urlparse(url)
        for proxy_type, url in proxies.items():
            req.set_proxy(url, proxy_type)
    rsp = request.urlopen(req)

    if isinstance(rsp, Response):
        downloader = cast(Response, rsp)
    else:
        downloader = ResponseWrapper(rsp)

    LOG.debug("Downloading url %s to %s", url, str(destination))
    downloader.download_file(destination, show_progress, digests)
