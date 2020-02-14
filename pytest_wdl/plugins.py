from collections import defaultdict
import logging
import os
from typing import (
    Dict, Generic, Iterable, Optional, Type, TypeVar, cast
)

from pkg_resources import EntryPoint, ResolutionError, iter_entry_points


LOG = logging.getLogger("pytest-wdl")
LOG.setLevel(os.environ.get("LOGLEVEL", "WARNING").upper())

T = TypeVar("T")


class PluginError(Exception):
    pass


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
            try:
                self.factory = self.entry_point.resolve()
            except ImportError as err:
                raise PluginError(
                    f"Could not load plugin {self.entry_point.name}"
                ) from err

        plugin = self.factory(*args, **kwargs)

        if not isinstance(plugin, self.return_type):  # TODO: test this
            raise RuntimeError(
                f"Expected plugin {plugin} to be an instance of {self.return_type}"
            )

        return cast(self.return_type, plugin)


def plugin_factory_map(
    return_type: Type[T],
    group: Optional[str] = None,
    entry_points: Optional[Iterable[EntryPoint]] = None
) -> Dict[str, PluginFactory[T]]:
    """
    Creates a mapping of entry point name to `PluginFactory` for all discovered
    entry points in the specified group.

    Args:
        group: Entry point group name
        return_type: Expected return type
        entry_points:

    Returns:
        Dict mapping entry point name to `PluginFactory` instances
    """
    if entry_points is None:
        entry_points = iter_entry_points(group=group)

    entry_point_map = defaultdict(list)

    for entry_point in entry_points:
        entry_point_map[entry_point.name].append(entry_point)

    factory_map = {}

    for name, points in entry_point_map.items():
        if len(points) > 1:
            # Filter out built-ins
            points = list(filter(
                lambda point: not point.module_name.startswith("pytest_wdl"), points
            ))
            if len(points) > 1:
                raise RuntimeError(
                    f"Multiple third-party plugins found in group {group} with the "
                    f"same name: {name}"
                )

        ep = points[0]

        try:
            ep.require()
        except ResourceWarning as rerr:
            LOG.warning(
                "Plugin %s is not available because it is missing an extra "
                "dependency: %s", name, str(rerr)
            )
            continue
        except ResolutionError as rerr:
            LOG.warning(
                "Plugin %s is not available because it is missing an extra "
                "dependency: %s", name, str(rerr)
            )
            continue
        except PluginError as perr:
            LOG.warning(
                "Error while loading plugin %s: %s", name, str(perr)
            )
            continue

        factory_map[name] = PluginFactory(ep, return_type)

    return factory_map
