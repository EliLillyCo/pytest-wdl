from unittest.mock import Mock

import pytest

from pytest_wdl.plugins import plugin_factory_map


def test_plugin_factory_map():
    ep1 = Mock()
    ep1.name = "foo"
    ep1.module_name = "pytest_wdl.foo"
    ep2 = Mock()
    ep2.name = "foo"
    ep2.module_name = "bar.baz"
    entry_points = [ep1, ep2]
    pfmap = plugin_factory_map(None, entry_points=entry_points)
    assert len(pfmap) == 1
    assert "foo" in pfmap
    assert pfmap["foo"].entry_point == ep2

    ep3 = Mock()
    ep3.name = "foo"
    ep3.module_name = "blorf.bleep"
    entry_points.append(ep3)
    with pytest.raises(RuntimeError):
        plugin_factory_map(None, entry_points=entry_points)
