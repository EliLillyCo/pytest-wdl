#! /usr/bin/env python
"""
Utility functions for pytest-wdl.
"""
import contextlib
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Dict, Generic, Optional, Sequence, Type, TypeVar, Union, cast

from pkg_resources import EntryPoint, iter_entry_points
from py._path.local import LocalPath


LOG = logging.getLogger("pytest-wdl")
LOG.setLevel(os.environ.get("LOGLEVEL", "WARNING").upper())

UNSAFE_RE = re.compile(r"[^\w.-]")

UNSET = object()

T = TypeVar("T")


class PluginFactory(Generic[T]):
    """
    Lazily loads a plugin class associated with a data type.
    """
    def __init__(self, entry_point: EntryPoint, return_type: Type[T]):
        self.entry_point = entry_point
        self.return_type = return_type
        self.factory = None

    def __call__(self, *args, **kwargs) -> T:
        if self.factory is None:
            module = __import__(
                self.entry_point.module_name, fromlist=['__name__'], level=0
            )
            self.factory = getattr(module, self.entry_point.attrs[0])
        plugin = self.factory(*args, **kwargs)
        if not isinstance(plugin, self.return_type):
            raise RuntimeError(
                f"Expected plugin {plugin} to be an instance of {self.return_type}"
            )
        return cast(self.return_type, plugin)


def plugin_factory_map(group: str, return_type: Type[T]) -> Dict[str, PluginFactory[T]]:
    """
    Creates a mapping of entry point name to `PluginFactory` for all discovered
    entry points in the specified group.

    Args:
        group: Entry point group name
        return_type: Expected return type

    Returns:
        Dict mapping entry point name to `PluginFactory` instances
    """
    return dict(
        (entry_point.name, PluginFactory(entry_point, return_type))
        for entry_point in iter_entry_points(group=group)
    )


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
def tempdir(change_dir: bool = False) -> Path:
    """
    Context manager that creates a temporary directory, yields it, and then
    deletes it after return from the yield.

    Args:
        change_dir: Whether to temporarily change to the temp dir.
    """
    temp = canonical_path(Path(tempfile.mkdtemp()))
    try:
        if change_dir:
            with chdir(temp):
                yield temp
        else:
            yield temp
    finally:
        shutil.rmtree(temp)


@contextlib.contextmanager
def context_dir(
    path: Optional[Path] = None, change_dir: bool = False,
    cleanup: Optional[bool] = None
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
            shutil.rmtree(path)


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
        check_path = canonical_path(project_root / path)
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
        if "PATH" in os.environ:
            search_path = [Path(p) for p in os.environ["PATH"].split(os.pathsep)]
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
        return os.environ.get(
            value_descriptor["env"], value_descriptor.get("value")
        )
    else:
        return value_descriptor.get("value")
