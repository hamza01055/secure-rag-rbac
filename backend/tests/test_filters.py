"""The filter must never be constructible in a permissive state."""
from __future__ import annotations

import dataclasses

import pytest

from app.core.errors import FilterError
from app.core.principal import Principal
from app.retrieval.filters import build_filter
from tests.conftest import make_principal


def test_filter_includes_all_three_predicates():
    flt = build_filter(make_principal("HR", 60, "tenant-a"))
    d = flt.as_dict()
    assert d["tenant_id"] == "tenant-a"
    assert d["allowed_roles_any_of"] == ["HR"]
    assert d["min_clearance_lte"] == 60


@pytest.mark.parametrize("field,value", [("tenant_id", ""), ("role", ""), ("clearance", -1)])
def test_incomplete_principal_raises(field, value):
    p = dataclasses.replace(make_principal(), **{field: value})
    with pytest.raises(FilterError):
        build_filter(p)


def test_admin_gets_no_bypass():
    """Admin is a role in the allowlist, not a branch that skips the filter."""
    flt = build_filter(make_principal("Admin", 100))
    assert not flt.is_empty()
    assert flt.roles == ["Admin"]


def test_principal_is_immutable():
    p = make_principal("Intern", 10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.clearance = 100        # type: ignore[misc]
