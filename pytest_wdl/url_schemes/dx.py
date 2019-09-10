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
from pathlib import Path

from typing import Sequence, Optional

import dxpy

from pytest_wdl.url_schemes import Method, Request, Response, UrlHandler


class DxResponse(Response):
    def __init__(self, file_id: str, project_id: Optional[str] = None):
        self.file_id = file_id
        self.project_id = project_id

    def download_file(self, destination: Path, show_progress: bool = False):
        dxpy.download_dxfile(
            self.file_id,
            str(destination),
            show_progress=show_progress,
            project=self.project_id
        )


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
        return DxResponse(file_id, project_id)
