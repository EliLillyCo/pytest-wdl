import logging
from typing import Sequence, Optional, cast
import urllib.request
from urllib.request import Request, urlopen

import pytest

from pytest_wdl.url_schemes import Response, BaseResponse, UrlHandler, Method
from pytest_wdl.localizers import download_file
from pytest_wdl.utils import tempdir

LOG = logging.getLogger(__name__)

try:
    # test whether dxpy is installed and the user is logged in
    import dxpy
    assert dxpy.SECURITY_CONTEXT
    assert dxpy.whoami()
    no_dx = False
except:
    no_dx = True


DX_SKIP_MSG = \
    "dxpy is not installed or user is not logged into a DNAnexus account; " \
    "DNAnexus URL handler will not be tested"
DX_FILE_ID = "file-BgY4VzQ0bvyg22pfZQpXfzgK"
DX_PROJECT_ID = "project-BQbJpBj0bvygyQxgQ1800Jkk"


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


@pytest.mark.skipif(no_dx, reason=DX_SKIP_MSG)
def test_dx():
    rsp = urlopen(f"dx://{DX_FILE_ID}")
    assert isinstance(rsp, Response)
    import pytest_wdl.url_schemes.dx
    assert isinstance(rsp, pytest_wdl.url_schemes.dx.DxResponse)
    with tempdir() as d:
        outfile = d / "readme.txt"
        cast(Response, rsp).download_file(outfile, False)
        assert outfile.exists()
        with open(outfile, "rt") as inp:
            txt = inp.read()
        assert txt.startswith("README.1st.txt")
        assert txt.rstrip().endswith(
            "SRR100022: Full exome to use as input to your analyses."
        )


@pytest.mark.skipif(no_dx, reason=DX_SKIP_MSG)
def test_dx_with_project():
    rsp = urlopen(f"dx://{DX_PROJECT_ID}:{DX_FILE_ID}")
    assert isinstance(rsp, Response)
    import pytest_wdl.url_schemes.dx
    assert isinstance(rsp, pytest_wdl.url_schemes.dx.DxResponse)
    with tempdir() as d:
        outfile = d / "readme.txt"
        cast(Response, rsp).download_file(outfile, False)
        assert outfile.exists()
        with open(outfile, "rt") as inp:
            txt = inp.read()
        assert txt.startswith("README.1st.txt")
        assert txt.rstrip().endswith(
            "SRR100022: Full exome to use as input to your analyses."
        )
