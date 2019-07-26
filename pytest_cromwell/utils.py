#! /usr/bin/env python
"""
Utility functions for pytest-cromwell.
"""
import contextlib
import logging
import os
from pathlib import Path
import shutil
import tempfile


LOG = logging.getLogger("pytest-cromwell")
LOG.setLevel(os.environ.get("LOGLEVEL", "WARNING").upper())


def deprecated(f):
    """
    Decorator for deprecated functions/methods. Deprecated functionality will be
    removed before each major release.
    """
    def decorator(*args, **kwargs):
        LOG.warning(f"Function/method {f.__name__} is deprecated and will be removed")
        f(*args, **kwargs)
    return decorator


@contextlib.contextmanager
def tempdir() -> Path:
    """
    Context manager that creates a temporary directory, yields it, and then
    deletes it after return from the yield.
    """
    temp = Path(tempfile.mkdtemp())
    try:
        yield temp
    finally:
        shutil.rmtree(temp)


@contextlib.contextmanager
def chdir(todir):
    """
    Context manager that temporarily changes directories.

    Args:
        todir: The directory to change to.
    """
    curdir = os.getcwd()
    try:
        os.chdir(todir)
        yield todir
    finally:
        os.chdir(curdir)


@contextlib.contextmanager
def test_dir(envar, project_root):
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
    testdir = os.environ.get(envar, None)
    cleanup = False
    if not testdir:
        testdir = tempfile.mkdtemp()
        cleanup = True
    else:
        if not os.path.isabs(testdir):
            testdir = os.path.abspath(os.path.join(project_root, testdir))
        if not os.path.exists(testdir):
            os.makedirs(testdir, exist_ok=True)
    try:
        yield testdir
    finally:
        if cleanup:
            shutil.rmtree(testdir)


def pypath_to_path(pypath) -> Path:
    """
    Converts a :class:`py.path.local.LocalPath` to a :class:`pathlib.Path`.

    Args:
        pypath: The path to convert.

    Returns:
        A Path
    """
    return Path(str(pypath))
