#!/usr/bin/env python3
"""Adversarial checks for a role-filtered RAG backend.

These are the tests that distinguish a working authorization filter from one
that happens to look like it works. Run against a seeded development stack, and
run in CI. A failure here is a release blocker.

    python scripts/verify_rbac.py --api http://localhost:8000

Requires a seeded corpus containing at least one document that exactly one role
can read, with a distinctive phrase that appears nowhere else. Set that phrase
with --canary. Without it, the suite cannot distinguish a correct filter from a
corpus where everything is public.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import httpx

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclass
class Results:
    rows: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))
        mark = {PASS: "  ok  ", FAIL: " FAIL ", SKIP: " skip "}[status]
        print(f"[{mark}] {name}" + (f"\n         {detail}" if detail else ""))

    @property
    def failed(self) -> int:
        return sum(1 for s, _, _ in self.rows if s == FAIL)


def login(client: httpx.Client, api: str, email: str, password: str) -> bool:
    r = client.post(f"{api}/auth/login", json={"email": email, "password": password})
    return r.status_code == 200


def chat(client: httpx.Client, api: str, query: str, **extra) -> httpx.Response:
    return client.post(f"{api}/chat", json={"query": query, **extra})


def run(api: str, canary: str, authorized: tuple[str, str],
        unauthorized: tuple[str, str], doc_id: str | None) -> Results:
    res = Results()

    # 1. The authorized user can reach the canary. Run this first: if it fails,
    #    every subsequent "blocked" result is meaningless, because a filter that
    #    blocks everyone looks identical to a correct one.
    with httpx.Client(timeout=30) as c:
        if not login(c, api, *authorized):
            res.add(FAIL, "authorized user can sign in")
            return res
        res.add(PASS, "authorized user can sign in")

        r = chat(c, api, canary)
        cited = r.json().get("citations", []) if r.status_code == 200 else []
        if r.status_code == 200 and cited:
            res.add(PASS, "authorized user retrieves the canary document",
                    f"{len(cited)} citation(s)")
        else:
            res.add(FAIL, "authorized user retrieves the canary document",
                    "the filter may be blocking everything — fix this before "
                    "trusting any result below")
            return res

    # 2. The unauthorized user gets nothing. Zero chunks, not a refusal message
    #    generated from chunks the model was shown.
    with httpx.Client(timeout=30) as c:
        if not login(c, api, *unauthorized):
            res.add(FAIL, "unauthorized user can sign in")
            return res

        r = chat(c, api, canary)
        body = r.json() if r.status_code == 200 else {}
        citations = body.get("citations", [])
        answer = (body.get("answer") or "").lower()

        if citations:
            res.add(FAIL, "unauthorized user retrieves zero chunks",
                    f"leaked {len(citations)} citation(s)")
        elif canary.lower() in answer:
            res.add(FAIL, "canary text absent from the answer",
                    "the model reproduced protected content")
        else:
            res.add(PASS, "unauthorized user retrieves zero chunks")

        # 3. A role supplied by the client must be ignored entirely.
        r = chat(c, api, canary, role="Admin", clearance=100)
        if r.status_code in (400, 422):
            res.add(PASS, "client-supplied role is rejected", f"HTTP {r.status_code}")
        elif r.status_code == 200 and not r.json().get("citations"):
            res.add(PASS, "client-supplied role is ignored")
        else:
            res.add(FAIL, "client-supplied role is ignored",
                    "privilege escalation via request body")

    # 4. Tampered and missing credentials fail before retrieval runs.
    with httpx.Client(timeout=30) as c:
        c.cookies.set("access_token", "not.a.real.token")
        r = chat(c, api, canary)
        if r.status_code == 401:
            res.add(PASS, "tampered token is rejected")
        else:
            res.add(FAIL, "tampered token is rejected", f"got HTTP {r.status_code}")

    with httpx.Client(timeout=30) as c:
        r = chat(c, api, canary)
        if r.status_code == 401:
            res.add(PASS, "unauthenticated request is rejected")
        else:
            res.add(FAIL, "unauthenticated request is rejected", f"got HTTP {r.status_code}")

    # 5. Deletion actually removes the vector points. Destructive, so opt in.
    if doc_id:
        with httpx.Client(timeout=60) as c:
            login(c, api, *authorized)
            d = c.delete(f"{api}/documents/{doc_id}")
            if d.status_code not in (200, 204):
                res.add(FAIL, "document delete succeeds", f"HTTP {d.status_code}")
            else:
                r = chat(c, api, canary)
                if r.json().get("citations"):
                    res.add(FAIL, "deleted document is unreachable",
                            "vector points survived deletion")
                else:
                    res.add(PASS, "deleted document is unreachable")
    else:
        res.add(SKIP, "deletion removes vector points", "pass --delete-doc-id to run")

    return res


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--canary", required=True,
                   help="phrase appearing only in the restricted document")
    p.add_argument("--authorized", nargs=2, metavar=("EMAIL", "PASSWORD"),
                   default=["hr@acme.test", "devpassword"])
    p.add_argument("--unauthorized", nargs=2, metavar=("EMAIL", "PASSWORD"),
                   default=["intern@acme.test", "devpassword"])
    p.add_argument("--delete-doc-id", default=None,
                   help="run the destructive deletion check against this document")
    a = p.parse_args()

    print(f"\nRBAC retrieval checks against {a.api}\n")
    res = run(a.api, a.canary, tuple(a.authorized), tuple(a.unauthorized), a.delete_doc_id)

    total = len(res.rows)
    print(f"\n{total - res.failed}/{total} checks passed\n")
    if res.failed:
        print("Authorization filtering is not verified. Do not deploy.\n")
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
