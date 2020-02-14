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
from enum import Enum
import functools
from pathlib import Path
from typing import Optional, Sequence
from urllib.request import BaseHandler, Request, build_opener, install_opener

from pkg_resources import iter_entry_points

from pytest_wdl.plugins import PluginError, PluginFactory
from pytest_wdl.utils import LOG, verify_digests

try:
    from tqdm import tqdm as progress
except ImportError:  # pragma: no-cover
    LOG.debug(
        "tqdm is not installed; progress bar will not be displayed when "
        "downloading files"
    )
    progress = None


class Method(Enum):
    OPEN = ("urlopen", "{}_open")
    REQUEST = ("request", "{}_request")
    RESPONSE = ("response", "{}_response")

    def __init__(self, src_attr, dest_pattern):
        self.src_attr = src_attr
        self.dest_pattern = dest_pattern


class Response(metaclass=ABCMeta):
    @abstractmethod
    def download_file(
        self,
        destination: Path,
        show_progress: bool = False,
        digests: Optional[dict] = None
    ):
        """
        Download a file to a specific destination.

        Args:
            destination: Destination path
            show_progress: Whether to show a progress bar
            digests: Optional dict mapping hash names to digests. These are used to
                validate the downloaded file.

        Raises:
            DigestsNotEqualError
        """
        pass


class BaseResponse(Response, metaclass=ABCMeta):
    @abstractmethod
    def get_content_length(self) -> Optional[int]:
        pass

    @abstractmethod
    def read(self, block_size: int):
        pass

    def download_file(
        self,
        destination: Path,
        show_progress: bool = False,
        digests: Optional[dict] = None
    ):
        total_size = self.get_content_length()
        block_size = 16 * 1024
        if total_size and total_size < block_size:
            block_size = total_size

        if show_progress and progress:
            progress_bar = progress(
                total=total_size,
                unit="b",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"Localizing {destination.name}"
            )

            def progress_reader():
                b = self.read(block_size)
                if b:
                    progress_bar.update(block_size)
                else:
                    progress_bar.close()
                return b

            reader = progress_reader
        else:
            reader = functools.partial(self.read, block_size)

        downloaded_size = 0

        with open(destination, "wb") as out:
            while True:
                buf = reader()
                if not buf:
                    break
                downloaded_size += len(buf)
                out.write(buf)

        if downloaded_size != total_size:  # TODO: test this
            raise AssertionError(
                f"Size of downloaded file {destination} does not match expected size "
                f"{total_size}"
            )

        if digests:
            verify_digests(destination, digests)


class ResponseWrapper(BaseResponse):
    def __init__(self, rsp):
        self.rsp = rsp

    def get_content_length(self) -> Optional[int]:
        size_str = self.rsp.getheader("content-length")
        if size_str:
            return int(size_str)

    def read(self, block_size: int) -> bytes:
        return self.rsp.read(block_size)


class UrlHandler(BaseHandler, metaclass=ABCMeta):
    @property
    @abstractmethod
    def scheme(self) -> str:
        pass

    @property
    def handles(self) -> Sequence[Method]:
        return []  # pragma: no-cover

    def alias(self):
        """
        Add aliases that are required by urllib for handled methods.
        """
        for method in self.handles:
            src = getattr(self, method.src_attr)
            setattr(self, method.dest_pattern.format(self.scheme), src)

    def request(self, request: Request) -> Request:
        pass

    def urlopen(self, request: Request) -> Response:
        pass

    def response(self, request: Request, response: Response) -> Response:
        pass


def install_schemes():
    def create_handler(_entry_point):
        handler_factory = PluginFactory(_entry_point, UrlHandler)
        handler = handler_factory()
        handler.alias()
        return handler

    handlers = []

    for entry_point in iter_entry_points(group="pytest_wdl.url_schemes"):
        try:
            handlers.append(create_handler(entry_point))
        except PluginError:
            pass

    install_opener(build_opener(*handlers))
