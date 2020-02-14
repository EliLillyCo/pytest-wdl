import logging
from typing import Sequence, Optional
import urllib.request
from urllib.request import Request

from pytest_wdl.url_schemes import Response, BaseResponse, UrlHandler, Method
from pytest_wdl.localizers import download_file
from pytest_wdl.utils import tempdir

LOG = logging.getLogger(__name__)


class MockResponse(BaseResponse):
    def __init__(self, url):
        self.content = url[6:]
        self.start = 0

    def get_content_length(self) -> Optional[int]:
        return len(self.content)

    def read(self, block_size: int):
        start = self.start
        end = min(start + block_size, len(self.content))
        if start == end:
            return None
        block = self.content[start:end]
        self.start = end
        return block.encode()


class MockHandler(UrlHandler):
    def __init__(self):
        self.request_called = False
        self.response_called = False

    @property
    def scheme(self) -> str:
        return "foo"

    @property
    def handles(self) -> Sequence[Method]:
        return [Method.OPEN, Method.REQUEST, Method.RESPONSE]

    def request(self, request: Request) -> Request:
        self.request_called = True
        return request

    def urlopen(self, request: Request) -> Response:
        return MockResponse(request.get_full_url())

    def response(self, request: Request, response: Response) -> Response:
        self.response_called = True
        return response


def test_url_schemes():
    opener = urllib.request._opener
    handler = MockHandler()
    handler.alias()
    try:
        urllib.request.install_opener(urllib.request.build_opener(handler))

        with tempdir() as d:
            outfile = d / "foo"
            download_file("foo://bar", outfile)
            with open(outfile, "rt") as inp:
                assert inp.read() == "bar"

        assert handler.request_called is True
        assert handler.response_called is True
    finally:
        urllib.request._opener = opener
