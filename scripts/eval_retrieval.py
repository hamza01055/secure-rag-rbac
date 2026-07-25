#!/usr/bin/env python3
"""Retrieval quality harness.

Runs a labeled eval set and reports recall, ranking quality, grounding, and —
deliberately in the same report — the permission leak rate.

Keeping the leak metric alongside the quality metrics is the point: it means
nobody can trade a point of nDCG for a leak without seeing it happen in the same
table.

Eval set format (JSON):

    {
      "queries": [
        {
          "id": "q1",
          "query": "what is the travel allowance",
          "as_user": "intern@acme.test",
          "relevant_chunk_docs": ["Employee_Handbook.md"],
          "forbidden_docs": ["Executive_Compensation_2026.md"]
        }
      ]
    }

`forbidden_docs` is what makes this a security test as well as a quality one: a
document listed there appearing in the results is a leak, at any ranking.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field

import httpx


@dataclass
class Metrics:
    recall_at_k: list[float] = field(default_factory=list)
    ndcg_at_k: list[float] = field(default_factory=list)
    reciprocal_rank: list[float] = field(default_factory=list)
    grounded: list[bool] = field(default_factory=list)
    leaks: list[str] = field(default_factory=list)

    def summary(self, k: int) -> str:
        def avg(xs):
            return sum(xs) / len(xs) if xs else 0.0
        lines = [
            f"queries evaluated     {len(self.recall_at_k)}",
            f"recall@{k:<15} {avg(self.recall_at_k):.3f}",
            f"nDCG@{k:<17} {avg(self.ndcg_at_k):.3f}",
            f"MRR                   {avg(self.reciprocal_rank):.3f}",
            f"grounded rate         {avg([1.0 if g else 0.0 for g in self.grounded]):.3f}",
            f"permission leaks      {len(self.leaks)}   <- must be 0",
        ]
        if self.leaks:
            lines.append("")
            lines.append("LEAKED ON:")
            lines.extend(f"  {q}" for q in self.leaks)
        return "\n".join(lines)


def ndcg(relevant: set[str], ranked: list[str], k: int) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def evaluate(api: str, evalset: dict, password: str, k: int) -> Metrics:
    m = Metrics()
    for case in evalset["queries"]:
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{api}/auth/login",
                       json={"email": case["as_user"], "password": password})
            if r.status_code != 200:
                print(f"  ! cannot sign in as {case['as_user']}", file=sys.stderr)
                continue

            resp = c.post(f"{api}/chat", json={"query": case["query"]})
            body = resp.json() if resp.status_code == 200 else {}

        citations = body.get("citations", [])
        ranked_docs = [c_.get("filename", "") for c_ in citations]

        forbidden = set(case.get("forbidden_docs", []))
        if forbidden & set(ranked_docs):
            m.leaks.append(f"{case['id']} ({case['as_user']})")

        relevant = set(case.get("relevant_chunk_docs", []))
        if relevant:
            hits = [d for d in ranked_docs[:k] if d in relevant]
            m.recall_at_k.append(len(set(hits)) / len(relevant))
            m.ndcg_at_k.append(ndcg(relevant, ranked_docs, k))
            rr = next((1 / (i + 1) for i, d in enumerate(ranked_docs) if d in relevant), 0.0)
            m.reciprocal_rank.append(rr)

        if body.get("grounded") is not None:
            m.grounded.append(bool(body["grounded"]))

    return m


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--evalset", default="scripts/evalset.json")
    p.add_argument("--password", default="devpassword")
    p.add_argument("-k", type=int, default=5)
    a = p.parse_args()

    with open(a.evalset) as fh:
        evalset = json.load(fh)

    print(f"\nRetrieval evaluation against {a.api}\n")
    m = evaluate(a.api, evalset, a.password, a.k)
    print(m.summary(a.k))
    print()
    return 1 if m.leaks else 0


if __name__ == "__main__":
    sys.exit(main())
