import contextlib
import random
import string

try:
    from pytest_wdl.providers.dx import dxpy
    assert dxpy
    NO_DX = False
except:
    NO_DX = True


DX_SKIP_MSG = \
    "dxpy is not installed or user is not logged into a DNAnexus account; " \
    "DNAnexus URL handler will not be tested"
DX_FILE_ID = "file-BgY4VzQ0bvyg22pfZQpXfzgK"
DX_PROJECT_ID = "project-BQbJpBj0bvygyQxgQ1800Jkk"


@contextlib.contextmanager
def random_project_folder(length: int = 8, prefix: str = "") -> str:
    """
    ContextManager that generates a random folder name, ensures that it doesn't
    already exist in the current project, yields it, and then deletes the folder if it
    exists.

    Returns:
        The folder path.
    """
    letters = string.ascii_letters + string.digits
    project = dxpy.DXProject(dxpy.PROJECT_CONTEXT_ID)

    while True:
        folder = "".join(random.choices(letters, k=length))
        folder_path = f"{prefix}{'' if prefix.endswith('/') else '/'}{folder}"
        try:
            project.list_folder(folder_path)
        except dxpy.exceptions.ResourceNotFound:
            # We found a folder that does not exist
            break

    try:
        yield folder_path
    finally:
        project.remove_folder(folder_path, recurse=True, force=True)
