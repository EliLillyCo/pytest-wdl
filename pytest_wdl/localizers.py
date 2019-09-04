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
import functools
from pathlib import Path
from typing import Optional, cast
from urllib import request

from pytest_wdl.config import UserConfiguration
from pytest_wdl.url_schemes import Response
from pytest_wdl.utils import LOG, env_map, resolve_value_descriptor, progress


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
        pass


class UrlLocalizer(Localizer):
    """
    Localizes a file specified by a URL.
    """
    def __init__(
        self,
        url: str,
        user_config: UserConfiguration,
        http_headers: Optional[dict] = None
    ):
        self.url = url
        self.user_config = user_config
        self._http_headers = http_headers

    def localize(self, destination: Path):
        try:
            download_file(
                self.url,
                destination,
                http_headers=self.http_headers,
                proxies=self.user_config.proxies,
                show_progress=self.user_config.show_progress
            )
        except Exception as err:
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
        with open(destination, "wt") as out:
            out.write(self.contents)


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
    show_progress: bool = True
):
    req = request.Request(url)
    if http_headers:
        for name, value in http_headers.items():
            req.add_header(name, value)
    if proxies:
        # TODO: Should we only set the proxy associated with the URL scheme?
        #  Should we raise an exception if there is not a proxy defined for
        #  the URL scheme?
        # parsed = parse.urlparse(url)
        for proxy_type, url in proxies.items():
            req.set_proxy(url, proxy_type)
    rsp = request.urlopen(req)

    if isinstance(rsp, Response):
        total_size = cast(Response, rsp).get_content_length()
    else:
        size_str = rsp.getheader("content-length")
        total_size = int(size_str) if size_str else None
    block_size = 16 * 1024
    if total_size and total_size < block_size:
        block_size = total_size

    LOG.debug("Downloading url %s to %s", url, str(destination))

    if show_progress and progress:
        progress_bar = progress(
            total=total_size,
            unit="b",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"Localizing {destination.name}"
        )

        def progress_reader():
            buf = rsp.read(block_size)
            if buf:
                progress_bar.update(block_size)
            else:
                progress_bar.close()
            return buf

        reader = progress_reader
    else:
        reader = functools.partial(rsp.read, block_size)

    with open(destination, "wb") as out:
        while True:
            buf = reader()
            if not buf:
                break
            out.write(buf)
