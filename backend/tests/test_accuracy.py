"""Accuracy layers. Each stage is tested for the failure it claims to fix."""
from __future__ import annotations

from app.accuracy import assembly, hybrid, query_rewrite, verification
from tests.conftest import make_chunk


def test_rrf_promotes_a_chunk_both_rankings_agree_on():
    a = make_chunk("a", "alpha", score=0.9)
    b = make_chunk("b", "beta", score=0.8)
    c = make_chunk("c", "gamma", score=0.7)
    fused = hybrid.reciprocal_rank_fusion([a, b, c], [c, a, b])
    assert fused[0].id in {"a", "c"}
    assert {x.id for x in fused} == {"a", "b", "c"}     # union, never widened


def test_rrf_with_one_empty_ranking_is_a_passthrough():
    a = make_chunk("a", "alpha")
    assert [c.id for c in hybrid.reciprocal_rank_fusion([a], [])] == ["a"]


def test_mmr_drops_near_duplicates():
    dup1 = make_chunk("1", "The reimbursement limit is 500 dollars per quarter", score=0.9)
    dup2 = make_chunk("2", "The reimbursement limit is 500 dollars per quarter", score=0.88)
    other = make_chunk("3", "Parking passes are issued by facilities", score=0.60)
    picked = assembly.mmr_select([dup1, dup2, other], k=2, lambda_=0.5)
    assert {c.id for c in picked} == {"1", "3"}


def test_token_budget_is_enforced():
    chunks = [make_chunk(str(i), "word " * 400, idx=i) for i in range(10)]
    kept = assembly.enforce_budget(chunks, token_budget=1000)
    assert 0 < len(kept) < 10


def test_query_rewrite_strips_filler_but_keeps_meaning():
    assert query_rewrite.normalize("Hey can you tell me the parental leave policy, thanks") \
        == "the parental leave policy"


def test_follow_up_is_condensed_with_history():
    out = query_rewrite.condense("what about their limit?", ["contractor expense policy"])
    assert "contractor expense policy" in out


def test_verification_flags_an_invented_figure():
    ctx = [make_chunk("1", "The travel allowance is 300 dollars per trip.")]
    report = verification.verify("The travel allowance is 900 dollars per trip.", ctx)
    assert not report.grounded
    assert report.unsupported_claims


def test_verification_accepts_a_grounded_answer():
    ctx = [make_chunk("1", "The travel allowance is 300 dollars per trip.")]
    report = verification.verify("The allowance is 300 dollars per trip. [1]", ctx)
    assert report.grounded


def test_an_answer_with_no_context_is_never_grounded():
    assert not verification.verify("The limit is 400 dollars.", []).grounded
