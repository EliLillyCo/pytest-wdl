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

# Todo: currently, the user is required to be logged into DNAnexus for this handler
#  to work properly. We should provide the ability to configure user account information
#  via the config file.

from typing import Sequence, Optional, cast

import dxpy

from pytest_wdl.url_schemes import Method, Request, Response, UrlHandler


class DxResponse(Response):
    def __init__(self, dx_file: dxpy.DXFile, url: str):
        try:
            self.desc = dx_file.describe()
            code = 200
        except dxpy.exceptions.DXAPIError as err:
            code = err.code
        super().__init__(dx_file, {}, url, code=code)

    def get_content_length(self) -> Optional[int]:
        return int(self.desc["size"])


class DxUrlHandler(UrlHandler):
    @property
    def scheme(self) -> str:
        return "dx"

    @property
    def handles(self) -> Sequence[Method]:
        return [Method.OPEN]

    def urlopen(self, request: Request) -> Response:
        url = request.get_full_url()
        if not url.startswith("dx://"):
            raise ValueError(f"Expected URL to start with 'dx://'; got {url}")
        obj_id = url[5:]
        if ":" in obj_id:
            project_id, file_id = obj_id.split(":")
        else:
            project_id = dxpy.PROJECT_CONTEXT_ID
            file_id = obj_id
        dx_file = dxpy.DXFile(file_id, project_id)
        return DxResponse(dx_file, url)
