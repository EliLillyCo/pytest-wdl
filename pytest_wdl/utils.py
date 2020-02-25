#! /usr/bin/env python
#
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
#
# TODO: some of the code here can be replaced by functions in xphyle.{paths,utils}
import contextlib
import fnmatch
import hashlib
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Callable, Optional, Sequence, Union, cast

from py._path.local import LocalPath


LOG = logging.getLogger("pytest-wdl")
LOG.setLevel(os.environ.get("LOGLEVEL", "WARNING").upper())

ENV_PATH = "PATH"
ENV_CLASSPATH = "CLASSPATH"
DEFAULT_CLASSPATH = "."

UNSAFE_RE = re.compile(r"[^\w.-]")


def safe_string(s: str, replacement: str = "_") -> str:
    """
    Makes a string safe by replacing non-word characters.

    Args:
        s: The string to make safe
        replacement: The replacement stringj

    Returns:
        The safe string
    """
    return UNSAFE_RE.sub(replacement, s)


# def deprecated(f: Callable):
#     """
#     Decorator for deprecated functions/methods. Deprecated functionality will be
#     removed before each major release.
#     """
#     def decorator(*args, **kwargs):
#         LOG.warning(f"Function/method {f.__name__} is deprecated and will be removed")
#         f(*args, **kwargs)
#     return decorator


@contextlib.contextmanager
def chdir(todir: Path):
    """
    Context manager that temporarily changes directories.

    Args:
        todir: The directory to change to.
    """
    curdir = Path.cwd()
    try:
        os.chdir(todir)
        yield todir
    finally:
        os.chdir(curdir)


@contextlib.contextmanager
def tempdir(
    change_dir: bool = False,
    tmproot: Optional[Path] = None,
    cleanup: Optional[bool] = True,
) -> Path:
    """
    Context manager that creates a temporary directory, yields it, and then
    deletes it after return from the yield.

    Args:
        change_dir: Whether to temporarily change to the temp dir.
        tmproot: Root directory in which to create temporary directories.
        cleanup: Whether to delete the temporary directory before exiting the context.
    """
    temp = ensure_path(tempfile.mkdtemp(dir=tmproot))
    try:
        if change_dir:
            with chdir(temp):
                yield temp
        else:
            yield temp
    finally:
        if cleanup:
            shutil.rmtree(temp)


@contextlib.contextmanager
def context_dir(
    path: Optional[Path] = None,
    change_dir: bool = False,
    cleanup: Optional[bool] = None,
) -> Path:
    """
    Context manager that looks for a specific environment variable to specify a
    directory. If the environment variable is not set, a temporary directory is
    created and cleaned up upon return from the yield.

    Args:
        path: The environment variable to look for.
        change_dir: Whether to change to the directory.
        cleanup: Whether to delete the directory when exiting the context. If None,
            the directory is only deleted if a temporary directory is created.

    Yields:
        A directory path.
    """
    if cleanup is None:
        cleanup = path is None

    if not path:
        path = Path(tempfile.mkdtemp())
    elif not path.exists():
        path.mkdir(parents=True)

    try:
        if change_dir:
            with chdir(path):
                yield path
        else:
            yield path
    finally:
        if cleanup and path.exists():
            shutil.rmtree(path, ignore_errors=True)


def ensure_path(
    path: Union[str, LocalPath, Path],
    search_paths: Optional[Sequence[Path]] = None,
    canonicalize: bool = True,
    exists: Optional[bool] = None,
    is_file: Optional[bool] = None,
    executable: Optional[bool] = None,
    create: bool = False,
) -> Path:
    """
    Converts a string path or :class:`py.path.local.LocalPath` to a
    :class:`pathlib.Path`.

    Args:
        path: The path to convert.
        search_paths: Directories to search for `path` if it is not already absolute.
            If `exists` is True, looks for the first search path that contains the file,
            otherwise just uses the first search path.
        canonicalize: Whether to return the canonicalized version of the path -
            expand home directory shortcut (~), make absolute, and resolve symlinks.
        exists: If True, raise an exception if the path does not exist; if False,
            raise an exception if the path does exist.
        is_file: If True, raise an exception if the path is not a file; if False,
            raise an exception if the path is not a directory.
        executable: If True and `is_file` is True and the file exists, raise an
            exception if it is not executable.
        create: Create the directory (or parent, if `is_file` = True) if
            it does not exist. Ignored if `exists` is True.

    Returns:
        A `pathlib.Path` object.
    """
    if isinstance(path, Path):
        p = cast(Path, path)
    else:
        p = Path(str(path))

    p = Path(os.path.expandvars(p))

    if canonicalize:
        p = p.expanduser()

        if search_paths and not p.is_absolute():
            if exists:
                for search_path in search_paths:
                    p_tmp = search_path / p
                    if p_tmp.exists():
                        p = p_tmp.absolute()
                        break
            else:
                p = (search_paths[0] / p).absolute()

        p = p.resolve()

    if p.exists():
        if exists is False:
            raise FileExistsError(f"Path {p} already exists")
        if is_file is True:
            if p.is_dir():
                raise IsADirectoryError(f"Path {p} is not a file")
            elif executable and not is_executable(p):
                raise OSError(f"File {p} is not executable")
        elif is_file is False and not p.is_dir():
            raise NotADirectoryError(f"Path {p} is not a directory")
    elif exists is True:
        raise FileNotFoundError(f"Path {p} does not exist")
    elif create:
        if is_file:
            p.parent.mkdir(parents=True, exist_ok=True)
        else:
            p.mkdir(parents=True, exist_ok=True)

    return p


def resolve_file(
    filename: Union[str, Path], project_root: Path, assert_exists: bool = True
) -> Optional[Path]:
    """
    Finds `filename` under `project_root` or in the project path.

    Args:
        filename: The filename, relative path, or absolute path to resolve.
        project_root: The project root dir.
        assert_exists: Whether to raise an error if the file cannot be found.

    Returns:
        A `pathlib.Path` object, or None if the file cannot be found and
        `assert_exists` is False.

    Raises:
        FileNotFoundError if the file cannot be found and `assert_exists` is True.
    """
    path = ensure_path(filename, canonicalize=False)
    is_abs = path.is_absolute()

    if is_abs and path.exists():
        return path

    if not is_abs:
        check_path = ensure_path(project_root / path)
        if check_path.exists():
            return check_path
        # Search in cwd
        check_path = find_project_path(path)
        if check_path and check_path.exists():
            return check_path
        # Search upward from project root
        check_path = find_project_path(path, start=project_root)
        if check_path and check_path.exists():
            return check_path

    if assert_exists:
        raise FileNotFoundError(f"Could not resolve file: {filename}")
    else:
        return None


def find_project_path(
    *filenames: Union[str, Path],
    start: Optional[Path] = None,
    return_parent: bool = False,
    assert_exists: bool = False,
) -> Optional[Path]:
    """
    Starting from `path` folder and moving upwards, search for any of `filenames` and
    return the first path containing any one of them.

    Args:
        *filenames: Filenames to search. Either a string filename, or a sequence of
            string path elements.
        start: Starting folder
        return_parent: Whether to return the containing folder or the discovered file.
        assert_exists: Whether to raise an exception if a file cannot be found.

    Returns:
        A `Path`, or `None` if no folder is found that contains any of `filenames`.
        If `return_parent` is `False` and more than one of the files is found one
        of the files is randomly selected for return.

    Raises:
        FileNotFoundError if the file cannot be found and `assert_exists` is True.
    """
    path = start or Path.cwd()
    while path != path.parent:
        for filename in filenames:
            if isinstance(filename, str):
                found = list(path.glob(filename))
                found = found[0] if found else None
            else:
                found = path / filename
                if not found.exists():
                    found = None
            if found:
                LOG.debug("Found %s in %s", filename, path)
                if return_parent:
                    return path
                else:
                    return found
        else:
            path = path.parent

    if assert_exists:
        raise FileNotFoundError(
            f"Could not find any of {','.join(str(f) for f in filenames)} "
            f"starting from {start}"
        )

    return None


def find_executable_path(
    executable: str, search_path: Optional[Sequence[Path]] = None
) -> Optional[Path]:
    """Finds 'executable' in `search_path`.

    Args:
        executable: The name of the executable to find.
        search_path: The list of directories to search. If None, the system search
            path (defined by the $PATH environment variable) is used.

    Returns:
        Absolute path of the executable, or None if no matching executable was found.
    """
    if search_path is None:
        if ENV_PATH in os.environ:
            search_path = [Path(p) for p in os.environ[ENV_PATH].split(os.pathsep)]
        else:
            return None
    for path in search_path:
        exe_path = path / executable
        if exe_path.exists() and is_executable(exe_path):
            return exe_path
    else:
        return None


def is_executable(path: Path) -> bool:
    """
    Checks if a path is executable.

    Args:
        path: The path to check

    Returns:
        True if `path` exists and is executable by the user, otherwise False.
    """
    return path.exists() and os.stat(path).st_mode & stat.S_IXUSR


def find_in_classpath(glob: str) -> Optional[Path]:
    """
    Attempts to find a .jar file matching the specified glob pattern in the
    Java classpath.

    Args:
        glob: JAR filename pattern

    Returns:
        Path to the JAR file, or None if a matching file is not found.
    """
    classpath = os.environ.get(ENV_CLASSPATH, DEFAULT_CLASSPATH)

    for path_str in classpath.split(os.pathsep):
        path = ensure_path(path_str)
        if path.exists():
            if path.is_dir():
                matches = list(path.glob(glob))
                if matches:
                    if len(matches) > 1:
                        LOG.warning(
                            "Found multiple jar files matching pattern %s: %s;"
                            "returning the first one.",
                            glob,
                            matches,
                        )
                    return matches[0]
            elif path.exists() and fnmatch.fnmatch(path.name, glob):
                return path


def env_map(d: dict) -> dict:
    """
    Given a mapping of keys to value descriptors, creates a mapping of the keys to
    the described values.
    """
    envmap = {}
    for name, value_descriptor in d.items():
        value = resolve_value_descriptor(value_descriptor)
        if value:
            envmap[name] = value
    return envmap


def resolve_value_descriptor(value_descriptor: Union[str, dict]) -> Optional:
    """
    Resolves the value of a value descriptor, which may be an environment variable
    name, or a map with keys `env` (the environment variable name) and `value` (the
    value to use if `env` is not specified or if the environment variable is unset.

    Args:
        value_descriptor:

    Returns:

    """
    if isinstance(value_descriptor, str):
        return os.environ.get(value_descriptor)
    elif "env" in value_descriptor:
        return os.environ.get(value_descriptor["env"], value_descriptor.get("value"))
    else:
        return value_descriptor.get("value")


class DigestsNotEqualError(AssertionError):
    pass


def compare_files_with_hash(file1: Path, file2: Path, hash_name: str = "md5"):
    file1_digest = hash_file(file1, hash_name)
    file2_digest = hash_file(file2, hash_name)
    if file1_digest != file2_digest:
        raise DigestsNotEqualError(
            f"{hash_name} digests differ between expected identical files "
            f"{file1}, {file2}"
        )


def hash_file(path: Path, hash_name: str = "md5") -> str:
    assert hash_name in hashlib.algorithms_guaranteed
    with open(path, "rb") as inp:
        hashobj = hashlib.new(hash_name)
        hashobj.update(inp.read())
        return hashobj.hexdigest()


def verify_digests(path: Path, digests: dict):
    for hash_name, expected_digest in digests.items():
        try:
            actual_digest = hash_file(path, hash_name)
        except AssertionError:  # TODO: test this
            LOG.warning(
                "Hash algorithm %s is not supported; cannot verify file %s",
                hash_name,
                path,
            )
            continue
        if actual_digest != expected_digest:
            raise DigestsNotEqualError(
                f"{hash_name} digest {actual_digest} of file "
                f"{path} does match expected value {expected_digest}"
            )


class PollingException(Exception):
    """Base exception that stores the last result seen."""
    def __init__(self, last=None):
        self.last = last


class TimeoutException(PollingException):
    """Exception raised if polling function times out"""


class MaxCallException(PollingException):
    """Exception raised if maximum number of iterations is exceeded"""


def poll(
    target: Callable,
    step: int = 1,
    args: Optional[Sequence] = None,
    kwargs: Optional[dict] = None,
    timeout: Optional[int] = None,
    max_tries: Optional[int] = None,
    check_success: Callable = bool,
    step_function: Optional[Callable[[int, int], int]] = None,
    ignore_exceptions: Sequence = (),
):
    """
    Poll by calling a target function until a certain condition is met. You must specify
    at least a target function to be called and the step -- base wait time between
    each function call.

    Vendored from the [polling](https://github.com/justiniso/polling) package.

    Args:
        target: The target callable
        step: Step defines the amount of time to wait (in seconds)
        args: Arguments to be passed to the target function
        kwargs: Keyword arguments to be passed to the target function
        timeout: The target function will be called until the time elapsed is greater
            than the maximum timeout (in seconds). NOTE that the actual execution
            time of the function *can* exceed the time specified in the timeout. For
            instance, if the target function takes 10 seconds to execute and the timeout
            is 21 seconds, the polling function will take a total of 30 seconds (two
            iterations of the target --20s which is less than the timeout--21s,
            and a final iteration)
        max_tries: Maximum number of times the target function will be called before
            failing
        check_success: A callback function that accepts the return value of the target
            function. It must return true if you want the polling function to stop
            and return this value. It must return false if you want to continue
            polling. You may also use this function to collect non-success values. The
            default is a callback that tests for truthiness (anything not False, 0,
            or empty collection).
        step_function: A callback function that accepts two arguments: current_step,
            num_tries; and returns the next step value. By default, this is constant,
            but you can also pass a function that will increase or decrease the step.
            As an example, you can increase the wait time between calling the target
            function by 10 seconds every iteration until the step is 100 seconds--at
            which point it should remain constant at 100 seconds

            >>> def my_step_function(current_step: int, num_tries: int) -> int:
            >>>     return max(current_step + 10, 100)

        ignore_exceptions: You can specify a tuple of exceptions that should be caught
            and ignored on every iteration. If the target function raises one of
            these exceptions, it will be caught and the exception instance will be
            pushed to the queue of values collected during polling. Any other exceptions
            raised will be raised as normal.

    Returns:
        The first value from the target function that meets the condions of the
        check_success callback. By default, this will be the first value that is not
        None, 0, False, '', or an empty collection.
    """
    max_time = time.time() + timeout if timeout else None
    tries = 0
    last_item = None

    if args is None:
        args = ()

    if kwargs is None:
        kwargs = {}

    while True:
        if max_tries and tries >= max_tries:
            raise MaxCallException(last_item)

        try:
            val = target(*args, **kwargs)
            last_item = val
        except ignore_exceptions as e:
            last_item = e
        else:
            # Condition passes, this is the only "successful" exit from the
            # polling function
            if check_success(val):
                return val

        tries += 1

        # Check the time after to make sure the poll function is called at least once
        if max_time and time.time() >= max_time:
            raise TimeoutException(last_item)

        time.sleep(step)

        if step_function:
            step = step_function(step, tries)
