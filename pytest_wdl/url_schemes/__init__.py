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
from typing import Optional, Sequence
from urllib.request import BaseHandler, Request, build_opener, install_opener
from urllib import response

from pkg_resources import iter_entry_points

from pytest_wdl.utils import PluginFactory


class Method(Enum):
    OPEN = ("urlopen", "{}_open")
    REQUEST = ("request", "{}_request")
    RESPONSE = ("response", "{}_response")

    def __init__(self, src_attr, dest_pattern):
        self.src_attr = src_attr
        self.dest_pattern = dest_pattern


class Response(response.addinfourl):
    def get_content_length(self) -> Optional[int]:
        return None


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
    def create_handler(entry_point):
        handler_factory = PluginFactory(entry_point, UrlHandler)
        handler = handler_factory()
        handler.alias()
        return handler

    handlers = [
        create_handler(entry_point)
        for entry_point in iter_entry_points(group="pytest_wdl.url_schemes")
    ]

    install_opener(build_opener(*handlers))
