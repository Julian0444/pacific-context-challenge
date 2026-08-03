"""Tests for Fase 4 — Ask mode: prompt building, citation validation, cache,
rate limiting, feature flag, provider error mapping, and session rules.

No network: the Anthropic client is faked via src.ask._get_client.
"""

import json
import re
import sys
from functools import partial
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from src import ask, auth
from src.main import app
from src.models import IncludedDocument, QueryRequest
from src.pipeline import run_pipeline
from src.workspaces import get_workspace


# ---------------------------------------------------------------------------
# Fixtures & fakes
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_ask_state():
    ask.reset_ask_state()
    yield
    ask.reset_ask_state()


@pytest.fixture()
def client():
    auth.reset_rate_limiter()
    c = TestClient(app)
    yield c
    auth.reset_rate_limiter()


@pytest.fixture()
def ask_key(monkeypatch):
    """Enable the feature flag with a dummy key (never used: client is faked)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")


class FakeMessagesAPI:
    """Stands in for client.messages. behavior: None → echo-cite the first
    doc in the prompt (+ one bogus id); str → fixed answer; Exception → raise."""

    def __init__(self, behavior=None):
        self.behavior = behavior
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.behavior, Exception):
            raise self.behavior
        if isinstance(self.behavior, str):
            answer = self.behavior
        else:
            found = re.search(r'<doc id="(doc_\d+)"', kwargs["messages"][0]["content"])
            first_id = found.group(1) if found else "doc_998"
            answer = (
                f"Grounded claim [{first_id}]. Repeat citation [{first_id}]. "
                "Fabricated citation [doc_999]."
            )
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=answer)],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=80),
            model="claude-haiku-4-5",
            stop_reason="end_turn",
        )


class FakeAnthropicClient:
    def __init__(self, behavior=None):
        self.messages = FakeMessagesAPI(behavior)


@pytest.fixture()
def fake_client(monkeypatch):
    fake = FakeAnthropicClient()
    monkeypatch.setattr(ask, "_get_client", lambda: fake)
    return fake


def _make_doc(doc_id="doc_001", content="Some content.", tokens=50, **kw):
    defaults = dict(
        doc_id=doc_id,
        content=content,
        score=0.9,
        freshness_score=0.8,
        tags=["tag"],
        token_count=tokens,
        title=f"Title {doc_id}",
        doc_type="memo",
        date="2024-01-01",
    )
    defaults.update(kw)
    return IncludedDocument(**defaults)


def _pe_pipeline_result(role="analyst", query="What is the IC recommendation for Meridian?"):
    """Run the real pipeline on pe-deal (full_policy) for prompt-safety tests."""
    from src.retriever import retrieve

    ws = get_workspace("pe-deal")
    request = QueryRequest(query=query, role=role, top_k=8, policy_name="full_policy")
    return ws, run_pipeline(request, partial(retrieve, workspace=ws.slug), ws.roles, ws.metadata)


# ---------------------------------------------------------------------------
# build_prompt (incl. the phase's key security test)
# ---------------------------------------------------------------------------

def test_build_prompt_includes_every_included_doc():
    docs = [_make_doc("doc_001", "Alpha content."), _make_doc("doc_002", "Beta content.")]
    system, user = ask.build_prompt("What happened?", docs)
    assert "ONLY" in system and "[doc_id]" in system
    for doc in docs:
        assert f'<doc id="{doc.doc_id}"' in user
        assert doc.content in user
    assert "What happened?" in user


def test_build_prompt_empty_context_states_no_documents():
    system, user = ask.build_prompt("Anything?", [])
    assert "no documents are available" in user


def test_build_prompt_sanitizes_metadata_attributes():
    doc = _make_doc("doc_001", "Body.", title='Weird "title" <script>')
    _, user = ask.build_prompt("q", [doc])
    doc_line = next(line for line in user.split("\n") if line.startswith("<doc "))
    assert "<script>" not in doc_line
    assert "Weird 'title' script" in doc_line


def test_blocked_documents_never_reach_the_prompt():
    """Security test of the phase: run the real pipeline as analyst, then
    assert nothing from the blocked (vp/partner) documents is in the prompt."""
    ws, result = _pe_pipeline_result(role="analyst")
    trace = result.trace
    assert trace.blocked_by_permission, "expected blocked docs for analyst"

    _, user = ask.build_prompt("What is the IC recommendation for Meridian?", result.context)

    # Rows are chunks (Fase 5 Etapa B): fingerprint every chunk of each
    # blocked parent document — none of them may appear in the prompt.
    with open(ws.index_docs_path) as f:
        rows = json.load(f)
    rows_by_doc: dict = {}
    for r in rows:
        rows_by_doc.setdefault(r.get("doc_id", r["id"]), []).append(r)
    for blocked in trace.blocked_by_permission:
        assert f'<doc id="{blocked.doc_id}"' not in user
        for row in rows_by_doc[blocked.doc_id]:
            fingerprint = row["excerpt"][:60]
            assert fingerprint not in user
    for included in result.context:
        assert f'<doc id="{included.doc_id}"' in user


# ---------------------------------------------------------------------------
# trim_to_context_cap
# ---------------------------------------------------------------------------

def test_trim_noop_under_cap():
    docs = [_make_doc(f"doc_{i:03d}", tokens=100) for i in range(3)]
    assert ask.trim_to_context_cap(docs, max_context_tokens=1000) == docs


def test_trim_cuts_in_packed_order_and_keeps_first():
    docs = [_make_doc(f"doc_{i:03d}", tokens=100) for i in range(5)]
    kept = ask.trim_to_context_cap(docs, max_context_tokens=250)
    assert [d.doc_id for d in kept] == ["doc_000", "doc_001"]
    # A single oversized doc is still kept (never send an empty prompt)
    assert ask.trim_to_context_cap([_make_doc(tokens=999)], max_context_tokens=10)


# ---------------------------------------------------------------------------
# extract_citations / grounded_doc_count
# ---------------------------------------------------------------------------

def test_citations_valid_invalid_and_deduped_in_order():
    answer = "Claim [doc_002]. More [doc_001]. Again [doc_002]. Fake [doc_999]."
    citations = ask.extract_citations(answer, ["doc_001", "doc_002"])
    assert [(c.doc_id, c.valid) for c in citations] == [
        ("doc_002", True), ("doc_001", True), ("doc_999", False),
    ]
    assert ask.grounded_doc_count(citations) == 2


def test_citations_empty_when_answer_has_none():
    assert ask.extract_citations("No citations here.", ["doc_001"]) == []


def test_citations_ignore_malformed_ids():
    citations = ask.extract_citations("Bad [doc_x] [DOC_001] [doc_12a] ok [doc_012]", ["doc_012"])
    assert [(c.doc_id, c.valid) for c in citations] == [("doc_012", True)]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_cache_roundtrip_and_ttl_expiry():
    key = ask.cache_key("pe-deal", "What Happened?", "analyst", "full_policy", 5)
    ask.cache_put(key, {"answer": "x"}, now=1000.0)
    assert ask.cache_get(key, now=1000.0 + 10) == {"answer": "x"}
    assert ask.cache_get(key, now=1000.0 + ask._cache_ttl_seconds() + 1) is None


def test_cache_key_normalizes_query_whitespace_and_case():
    a = ask.cache_key("pe-deal", "  What   HAPPENED? ", "analyst", "full_policy", 5)
    b = ask.cache_key("pe-deal", "what happened?", "analyst", "full_policy", 5)
    c = ask.cache_key("pe-deal", "what happened?", "vp", "full_policy", 5)
    assert a == b and b != c


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def test_rate_limit_per_ip_blocks_and_window_clears(monkeypatch):
    monkeypatch.setenv("ASK_MAX_PER_MINUTE", "2")
    assert ask.allow_ask("1.1.1.1", now=100.0)
    assert ask.allow_ask("1.1.1.1", now=101.0)
    assert not ask.allow_ask("1.1.1.1", now=102.0)
    assert ask.allow_ask("2.2.2.2", now=102.0)  # other IP unaffected
    assert ask.allow_ask("1.1.1.1", now=100.0 + ask.RATE_WINDOW_SECONDS + 2)


def test_rate_limit_global_blocks_across_ips(monkeypatch):
    monkeypatch.setenv("ASK_MAX_PER_MINUTE", "10")
    monkeypatch.setenv("ASK_MAX_PER_MINUTE_GLOBAL", "3")
    for i in range(3):
        assert ask.allow_ask(f"10.0.0.{i}", now=200.0)
    assert not ask.allow_ask("10.0.0.99", now=201.0)


# ---------------------------------------------------------------------------
# call_model — content extraction
# ---------------------------------------------------------------------------

def test_call_model_joins_text_blocks_and_ignores_others(monkeypatch, ask_key):
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="..."),
            SimpleNamespace(type="text", text="Part one. "),
            SimpleNamespace(type="text", text="Part two."),
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        model="claude-haiku-4-5",
        stop_reason="end_turn",
    )
    fake = FakeAnthropicClient()
    fake.messages.create = lambda **kw: message
    monkeypatch.setattr(ask, "_get_client", lambda: fake)
    reply = ask.call_model("sys", "user")
    assert reply.text == "Part one. Part two."
    assert reply.usage.input_tokens == 10 and reply.usage.output_tokens == 5


def test_call_model_empty_content_gets_fallback_text(monkeypatch, ask_key):
    message = SimpleNamespace(
        content=[],
        usage=SimpleNamespace(input_tokens=10, output_tokens=0),
        model="claude-haiku-4-5",
        stop_reason="refusal",
    )
    fake = FakeAnthropicClient()
    fake.messages.create = lambda **kw: message
    monkeypatch.setattr(ask, "_get_client", lambda: fake)
    assert "no answer" in ask.call_model("sys", "user").text


# ---------------------------------------------------------------------------
# /ask endpoint — feature flag & health
# ---------------------------------------------------------------------------

def test_ask_403_and_health_false_without_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/health").json()["ask_enabled"] is False
    resp = client.post("/ask", json={"query": "anything", "role": "analyst"})
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"]


def test_health_ask_enabled_with_key(client, ask_key):
    assert client.get("/health").json()["ask_enabled"] is True


# ---------------------------------------------------------------------------
# /ask endpoint — happy path, cache, rate limit, errors
# ---------------------------------------------------------------------------

_ASK_BODY = {
    "query": "What is the IC recommendation for Meridian?",
    "role": "partner",
    "policy_name": "full_policy",
}


def test_ask_response_shape(client, ask_key, fake_client):
    resp = client.post("/ask", json=_ASK_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"].startswith("Grounded claim")
    assert body["model"] == "claude-haiku-4-5"
    assert body["usage"] == {"input_tokens": 1200, "output_tokens": 80}
    assert body["cached"] is False
    assert body["context"] and body["decision_trace"]["included"]
    assert body["total_tokens"] == body["decision_trace"]["total_tokens"]
    # echo-cite fake: first citation is a real context doc, doc_999 is fabricated
    cited = {c["doc_id"]: c["valid"] for c in body["citations"]}
    first_doc = body["context"][0]["doc_id"]
    assert cited[first_doc] is True
    assert cited["doc_999"] is False
    assert body["grounded_doc_count"] == 1
    # the model call carried the governed context, not the raw corpus
    prompt = fake_client.messages.calls[0]["messages"][0]["content"]
    assert f'<doc id="{first_doc}"' in prompt


def test_ask_cache_second_call_is_free_and_marked(client, ask_key, fake_client):
    first = client.post("/ask", json=_ASK_BODY).json()
    second = client.post("/ask", json={**_ASK_BODY, "query": "  what IS the ic RECOMMENDATION for meridian?  "}).json()
    assert len(fake_client.messages.calls) == 1  # normalized query → cache hit
    assert first["cached"] is False and second["cached"] is True
    assert second["answer"] == first["answer"]


def test_ask_rate_limit_429(client, ask_key, fake_client, monkeypatch):
    monkeypatch.setenv("ASK_MAX_PER_MINUTE", "1")
    assert client.post("/ask", json=_ASK_BODY).status_code == 200
    resp = client.post("/ask", json={**_ASK_BODY, "query": "different question"})
    assert resp.status_code == 429
    assert "cache" in resp.json()["detail"]


def test_ask_rate_limit_keys_on_forwarded_for(client, ask_key, fake_client, monkeypatch):
    monkeypatch.setenv("ASK_MAX_PER_MINUTE", "1")
    assert client.post(
        "/ask", json=_ASK_BODY, headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.1"}
    ).status_code == 200
    # different forwarded IP → separate window
    assert client.post(
        "/ask", json={**_ASK_BODY, "query": "second question"},
        headers={"X-Forwarded-For": "8.8.8.8"},
    ).status_code == 200


@pytest.mark.parametrize("exc_factory, fragment", [
    (lambda req: __import__("anthropic").APITimeoutError(request=req), "timed out"),
    (lambda req: __import__("anthropic").APIConnectionError(request=req), "reach"),
    (lambda req: __import__("anthropic").InternalServerError(
        "boom", response=httpx.Response(500, request=httpx.Request("POST", "https://x")), body=None
    ), "HTTP 500"),
    (lambda req: __import__("anthropic").RateLimitError(
        "slow down", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None
    ), "rate-limiting"),
    (lambda req: __import__("anthropic").AuthenticationError(
        "bad key", response=httpx.Response(401, request=httpx.Request("POST", "https://x")), body=None
    ), "API key"),
])
def test_ask_provider_failures_map_to_502(client, ask_key, monkeypatch, exc_factory, fragment):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake = FakeAnthropicClient(behavior=exc_factory(req))
    monkeypatch.setattr(ask, "_get_client", lambda: fake)
    resp = client.post("/ask", json=_ASK_BODY)
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert fragment in detail
    assert "Traceback" not in detail


def test_ask_unknown_role_400(client, ask_key, fake_client):
    resp = client.post("/ask", json={"query": "q", "role": "root"})
    assert resp.status_code == 400
    assert "Unknown role" in resp.json()["detail"]


def test_ask_other_workspace(client, ask_key, fake_client):
    resp = client.post("/ask", json={
        "query": "What changed in the on-call runbook?",
        "role": "employee",
        "workspace": "saas-internal",
    })
    assert resp.status_code == 200
    assert resp.json()["decision_trace"]["user_context"]["role"] == "employee"


# ---------------------------------------------------------------------------
# /ask endpoint — session rules (Fase P) & redaction
# ---------------------------------------------------------------------------

def _login(c, username, password):
    return c.post("/login", json={"username": username, "password": password})


def test_ask_session_conflicting_role_400(client, ask_key, fake_client):
    assert _login(client, "julia", "demo-analyst").status_code == 200
    resp = client.post("/ask", json={"query": "q", "role": "partner"})
    assert resp.status_code == 400
    assert "derived from your session" in resp.json()["detail"]


def test_ask_non_admin_conflicting_policy_400(client, ask_key, fake_client):
    assert _login(client, "julia", "demo-analyst").status_code == 200
    resp = client.post("/ask", json={"query": "q", "policy_name": "naive_top_k"})
    assert resp.status_code == 400


def test_ask_workspace_binding_403(client, ask_key, fake_client):
    assert _login(client, "julia", "demo-analyst").status_code == 200
    resp = client.post("/ask", json={"query": "q", "workspace": "saas-internal"})
    assert resp.status_code == 403


def test_ask_redaction_per_viewer_even_from_cache(client, ask_key, fake_client):
    """Cache stores the full trace; redaction is applied per viewer at serve
    time. Guest (lab) sees blocked docs; julia, served the SAME cache entry,
    must not."""
    body = {"query": _ASK_BODY["query"], "role": "analyst", "policy_name": "full_policy"}
    guest = client.post("/ask", json=body).json()
    assert guest["decision_trace"]["blocked_by_permission"], "analyst query should block docs"
    assert guest["cached"] is False

    assert _login(client, "julia", "demo-analyst").status_code == 200
    julia = client.post("/ask", json={"query": body["query"]}).json()
    assert julia["cached"] is True  # same (workspace, query, role, policy, top_k)
    assert julia["answer"] == guest["answer"]
    trace = julia["decision_trace"]
    assert trace["blocked_by_permission"] == []
    # blocked entries are per-chunk; the summary counts unique parent docs
    guest_blocked_docs = {b["doc_id"] for b in guest["decision_trace"]["blocked_by_permission"]}
    assert trace["blocked_summary"]["count"] == len(guest_blocked_docs)
    assert len(fake_client.messages.calls) == 1


def test_ask_prompt_leak_check_at_api_boundary(client, ask_key, fake_client):
    """As julia (analyst), the prompt sent to the provider must not contain
    any vp/partner document content."""
    assert _login(client, "julia", "demo-analyst").status_code == 200
    resp = client.post("/ask", json={"query": "customer concentration risk for Meridian"})
    assert resp.status_code == 200

    ws = get_workspace("pe-deal")
    with open(ws.index_docs_path) as f:
        indexed = json.load(f)
    analyst_rank = ws.roles["analyst"]["access_rank"]
    prompt = fake_client.messages.calls[0]["messages"][0]["content"]
    above_analyst = [
        d for d in indexed
        if ws.roles[d["min_role"]]["access_rank"] > analyst_rank
    ]
    assert above_analyst
    for doc in above_analyst:
        assert doc["excerpt"][:60] not in prompt
        assert f'<doc id="{doc["id"]}"' not in prompt


# ---------------------------------------------------------------------------
# evaluator --ask / --ask-goldens (Fase 4.4 — mocked model, no network)
# ---------------------------------------------------------------------------

def _cite_everything(system, user):
    """Fake model: cites every doc id present in the prompt."""
    ids = re.findall(r'<doc id="(doc_\d+)"', user)
    text = " ".join(f"Claim grounded in [{i}]." for i in ids) or "Insufficient context."
    return ask.ModelReply(text=text, model="fake-model", input_tokens=100, output_tokens=20)


def _cite_garbage(system, user):
    return ask.ModelReply(
        text="Everything is fine [doc_999].", model="fake-model",
        input_tokens=100, output_tokens=10,
    )


def test_run_ask_evals_faithful_citations():
    from src.evaluator import load_test_queries, run_ask_evals

    ws = get_workspace("pe-deal")
    queries = load_test_queries(ws.evals_path)[:3]
    results = run_ask_evals(queries, top_k=8, workspace="pe-deal", call=_cite_everything)

    agg = results["aggregate"]
    assert agg["queries_run"] == 3
    assert agg["citation_validity_rate"] == 1.0
    assert agg["groundedness_rate"] == 1.0
    # benchmark recall is 1.0 on this corpus, so citing the whole context
    # necessarily covers the expected docs
    assert agg["expected_cited_rate"] == 1.0
    assert agg["model"] == "fake-model"
    assert agg["total_input_tokens"] == 300


def test_run_ask_evals_flags_fabricated_citations():
    from src.evaluator import load_test_queries, run_ask_evals

    ws = get_workspace("pe-deal")
    queries = load_test_queries(ws.evals_path)[:2]
    results = run_ask_evals(queries, top_k=8, workspace="pe-deal", call=_cite_garbage)

    agg = results["aggregate"]
    assert agg["citation_validity_rate"] == 0.0
    assert agg["groundedness_rate"] == 0.0
    assert all(r["invalid_citations"] == ["doc_999"] for r in results["per_query"])


def test_run_ask_goldens_builds_role_pairs_without_writing():
    from src.evaluator import run_ask_goldens

    with open("corpora/pe-deal/ask_goldens.json") as f:
        on_disk_before = f.read()

    goldens = run_ask_goldens(workspace="pe-deal", call=_cite_everything, write=False)
    entries = goldens["snapshots"]["entries"]
    cases = goldens["cases"]
    assert len(entries) == sum(len(c["roles"]) for c in cases)
    ic_entries = {e["role"]: e for e in entries if e["case_id"] == "golden_ic_recommendation"}
    assert set(ic_entries) == {"analyst", "partner"}
    # partner sees (and cites) the partner-only IC memo; analyst cannot
    partner_cited = {c["doc_id"] for c in ic_entries["partner"]["citations"]}
    analyst_cited = {c["doc_id"] for c in ic_entries["analyst"]["citations"]}
    assert "doc_010" in partner_cited
    assert "doc_010" not in analyst_cited
    assert ic_entries["analyst"]["blocked_count"] > 0
    # nothing was persisted — write=False leaves the on-disk file byte-identical
    # (it may already carry measured snapshots from a keyed --ask-goldens run)
    with open("corpora/pe-deal/ask_goldens.json") as f:
        assert f.read() == on_disk_before


def test_evaluator_cli_ask_requires_key(monkeypatch):
    import src.evaluator as evaluator

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for flag in ("--ask", "--ask-goldens"):
        monkeypatch.setattr(sys, "argv", ["evaluator", flag])
        with pytest.raises(SystemExit) as exc:
            evaluator.main()
        assert exc.value.code == 2  # argparse error, clear message, no network
