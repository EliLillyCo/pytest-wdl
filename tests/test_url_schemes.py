import io
from typing import Sequence
import urllib.request
from urllib.request import Request

from pytest_wdl.url_schemes import Response, UrlHandler, Method
from pytest_wdl.localizers import download_file
from pytest_wdl.utils import tempdir


class MockResponse(Response):
    def __init__(self, url):
        mock_fp = io.BytesIO(url[6:].encode())
        super().__init__(mock_fp, {}, url, 200)


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
