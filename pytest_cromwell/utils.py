#! /usr/bin/env python
"""
Utility functions for pytest-cromwell.
"""
import contextlib
import logging
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Optional, Sequence, Union, cast

from py._path.local import LocalPath


LOG = logging.getLogger("pytest-cromwell")
LOG.setLevel(os.environ.get("LOGLEVEL", "WARNING").upper())


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
def tempdir() -> Path:
    """
    Context manager that creates a temporary directory, yields it, and then
    deletes it after return from the yield.
    """
    temp = canonical_path(Path(tempfile.mkdtemp()))
    try:
        yield temp
    finally:
        shutil.rmtree(temp)


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
def test_dir(envar: str, project_root: Optional[Path] = None) -> Path:
    """
    Context manager that looks for a specific environment variable to specify a
    directory. If the environment variable is not set, a temporary directory is
    created and cleaned up upon return from the yield.

    Args:
        envar: The environment variable to look for.
        project_root: The root directory to use when the path is relative.

    Yields:
        A directory path.
    """
    testdir = os.environ.get(envar)
    cleanup = False
    if not testdir:
        testdir_path = Path(tempfile.mkdtemp())
        cleanup = True
    else:
        testdir_path = to_path(testdir, project_root)
        if not testdir_path.exists():
            testdir_path.mkdir(parents=True)
    try:
        yield testdir_path
    finally:
        if cleanup and testdir_path.exists():
            shutil.rmtree(testdir_path)


def to_path(
    path: Union[str, LocalPath, Path], root: Optional[Path] = None,
    canonicalize: bool = False
) -> Path:
    """
    Converts a string path or :class:`py.path.local.LocalPath` to a
    :class:`pathlib.Path`.

    Args:
        path: The path to convert.
        root: Root directory to use to make `path` absolute if it is not already.
        canonicalize: Whether to return the canonicalized version of the path.

    Returns:
        A `pathlib.Path` object.
    """
    if isinstance(path, Path):
        p = cast(Path, path)
    else:
        p = Path(str(path))
    if root and not p.is_absolute():
        p = root / p
        canonicalize = True
    if canonicalize:
        p = canonical_path(p)
    return p


def canonical_path(path: Path) -> Path:
    """
    Get the canonical path for a Path - esxpand home directory shortcut (~),
    make absolute, and resolve symlinks.
    """
    return path.expanduser().absolute().resolve()


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
    path = to_path(filename)
    is_abs = path.is_absolute()

    if is_abs and path.exists():
        return path

    if not is_abs:
        test_path = canonical_path(project_root / path)
        if test_path.exists():
            return test_path
        # Search in cwd
        test_path = find_project_path(path)
        if test_path and test_path.exists():
            return test_path
        # Search upward from project root
        test_path = find_project_path(path, start=project_root)
        if test_path and test_path.exists():
            return test_path

    if assert_exists:
        raise FileNotFoundError(f"Could not resolve file: {filename}")
    else:
        return None


def find_project_path(
    *filenames: Union[str, Path],
    start: Optional[Path] = None,
    return_parent: bool = False,
    assert_exists: bool = False
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
        search_path = [Path(p) for p in os.environ['PATH'].split(os.pathsep)]
    for path in search_path:
        exe_path = path / executable
        if exe_path.exists() and (os.stat(exe_path).st_mode & stat.S_IXUSR):
            return exe_path
    else:
        return None
