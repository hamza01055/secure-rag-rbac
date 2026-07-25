"""Construction of the authorization predicate.

This module has one job and no fallbacks. If it cannot build a complete filter
it raises, and the caller aborts. There is deliberately no code path that
returns None, an empty filter, or a permissive default — an empty filter matches
everything, which is the single worst bug this system can have.
"""
from __future__ import annotations

from app.core.errors import FilterError
from app.core.principal import Principal
from app.vector.base import SearchFilter


def build_filter(principal: Principal) -> SearchFilter:
    if not principal.tenant_id:
        raise FilterError("principal has no tenant")
    if not principal.role:
        raise FilterError("principal has no role")
    if principal.clearance is None or principal.clearance < 0:
        raise FilterError("principal has no valid clearance")

    flt = SearchFilter(
        tenant_id=principal.tenant_id,
        roles=[principal.role],
        clearance=principal.clearance,
    )

    # Admin gets no bypass branch. Admin is a role that appears in the
    # allowed_roles of every document, enforced at ingest. A code path that
    # skips the filter for "trusted" callers is the code path that gets reused
    # by accident six months from now.
    if flt.is_empty():
        raise FilterError("refusing to produce an empty authorization filter")
    return flt
