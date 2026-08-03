"""
ask.py — Ask mode: close the RAG loop with auditable citations (Fase 4).

POST /ask runs the exact same governed pipeline as /query and hands the
packed context to a Claude model. This module owns everything around that
call, and everything except call_model() is pure/testable without network:

- build_prompt():        the prompt IS the audited context — only documents
                         the pipeline included ever reach the model.
- extract_citations():   mechanical [doc_id] validation, no LLM judge.
- cache_*():             per-(workspace, query, role, policy, top_k) TTL cache
                         so repeating a demo query never re-spends tokens.
- allow_ask():           in-process per-IP + global rate limit (429 upstream).
- call_model():          the single network touchpoint; SDK errors map to
                         AskUpstreamError (→ 502 at the HTTP boundary).

Feature flag: the mode exists only when ANTHROPIC_API_KEY is set — /health
exposes ask_enabled and the frontend hides the button otherwise. Removing
the env var is the kill-switch.
"""

import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from src.models import AskUsage, Citation, IncludedDocument

# Model + generation knobs. ASK_MODEL default is Haiku (cheapest current
# model, ~$1/$5 per MTok) — a public-demo cost decision, overridable per deploy.
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_MAX_TOKENS = 600
DEFAULT_TEMPERATURE = "0.2"  # "none" disables the param (newer models reject it)
DEFAULT_TIMEOUT_SECONDS = 30.0

# Guardrails for the public demo.
DEFAULT_CACHE_TTL_SECONDS = 3600.0
MAX_CACHE_ENTRIES = 256
RATE_WINDOW_SECONDS = 60.0
DEFAULT_MAX_PER_MINUTE = 6  # per IP
DEFAULT_MAX_PER_MINUTE_GLOBAL = 30
# Defensive second belt on prompt size: the budget packer already caps
# context at policy.token_budget (2048); this guards against future policy
# changes silently inflating the paid prompt.
DEFAULT_MAX_CONTEXT_TOKENS = 4096

SYSTEM_PROMPT = (
    "You answer questions using ONLY the documents provided in the context. "
    "After each claim, cite the supporting document as [doc_id], e.g. [doc_003]. "
    "Cite only ids that appear in the context. If the context is insufficient "
    "to answer, say so explicitly — do not use outside knowledge."
)

_CITATION_RE = re.compile(r"\[(doc_\d+)\]")


class AskUpstreamError(Exception):
    """Provider-side failure (timeout, 5xx, auth, rate limit) → HTTP 502."""


@dataclass(frozen=True)
class ModelReply:
    """What call_model() returns — the raw material for AskResponse."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: Optional[str] = None

    @property
    def usage(self) -> AskUsage:
        return AskUsage(input_tokens=self.input_tokens, output_tokens=self.output_tokens)


def ask_enabled() -> bool:
    """Ask mode exists only when an API key is configured (read per request)."""
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


# ---------------------------------------------------------------------------
# Prompt building (pure — the security-critical function of the phase)
# ---------------------------------------------------------------------------

def _attr(value: Optional[str]) -> str:
    """Sanitize a metadata value for use inside a <doc ...> attribute."""
    return (value or "").replace('"', "'").replace("<", "").replace(">", "")


def trim_to_context_cap(
    docs: List[IncludedDocument], max_context_tokens: Optional[int] = None
) -> List[IncludedDocument]:
    """Defensive cap on prompt size, on top of the budget packer's own limit.

    Keeps documents in packed order until the cumulative token_count would
    exceed the cap. With the default policy budget (2048) this never trims.
    """
    cap = (
        max_context_tokens
        if max_context_tokens is not None
        else int(os.getenv("ASK_MAX_CONTEXT_TOKENS", str(DEFAULT_MAX_CONTEXT_TOKENS)))
    )
    kept: List[IncludedDocument] = []
    used = 0
    for doc in docs:
        if kept and used + doc.token_count > cap:
            break
        kept.append(doc)
        used += doc.token_count
    return kept


def build_prompt(query: str, included_docs: List[IncludedDocument]) -> Tuple[str, str]:
    """Build (system, user) for the model call.

    The user prompt embeds exactly the documents the pipeline packed —
    blocked documents never reach this function, so they can never leak
    into the prompt. Pure function: no I/O, trivially testable.

    Packed items are chunks (Fase 5 Etapa B): sibling chunks of the same
    document are grouped into ONE <doc> block, in chunk order, so citations
    stay doc-level ([doc_003]) and the model never sees duplicate ids.
    """
    if included_docs:
        grouped: dict = {}
        for doc in included_docs:
            grouped.setdefault(doc.doc_id, []).append(doc)
        blocks = []
        for doc_id, parts in grouped.items():
            parts = sorted(parts, key=lambda d: d.chunk_index or 0)
            head = parts[0]
            body = "\n[...]\n".join(p.content for p in parts)
            blocks.append(
                f'<doc id="{doc_id}" title="{_attr(head.title)}" '
                f'date="{_attr(head.date)}" type="{_attr(head.doc_type)}">\n'
                f"{body}\n</doc>"
            )
        context_section = "\n".join(blocks)
    else:
        context_section = "(no documents are available to you for this question)"
    user = f"Question: {query}\n\nContext documents:\n{context_section}"
    return SYSTEM_PROMPT, user


# ---------------------------------------------------------------------------
# Citation extraction + validation (mechanical, no LLM judge)
# ---------------------------------------------------------------------------

def extract_citations(answer: str, included_ids: Iterable[str]) -> List[Citation]:
    """All [doc_id] citations in the answer, deduped in order of appearance.

    A citation is valid iff the id was in the context the model saw.
    """
    valid_ids: Set[str] = set(included_ids)
    seen: List[str] = []
    for match in _CITATION_RE.finditer(answer):
        doc_id = match.group(1)
        if doc_id not in seen:
            seen.append(doc_id)
    return [Citation(doc_id=doc_id, valid=doc_id in valid_ids) for doc_id in seen]


def grounded_doc_count(citations: List[Citation]) -> int:
    return sum(1 for c in citations if c.valid)


# ---------------------------------------------------------------------------
# Response cache (per workspace/query/role/policy/top_k, TTL)
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: Dict[tuple, tuple] = {}  # key -> (expires_at, response)


def _cache_ttl_seconds() -> float:
    return float(os.getenv("ASK_CACHE_TTL_SECONDS", str(DEFAULT_CACHE_TTL_SECONDS)))


def cache_key(
    workspace: str, query: str, role: str, policy_name: str, top_k: int
) -> tuple:
    normalized = " ".join(query.lower().split())
    return (workspace, normalized, role, policy_name, top_k)


def cache_get(key: tuple, now: Optional[float] = None):
    """Return the cached response for `key`, or None (expired entries drop)."""
    ts = now if now is not None else time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, response = entry
        if ts >= expires_at:
            del _cache[key]
            return None
        return response


def cache_put(key: tuple, response, now: Optional[float] = None) -> None:
    ts = now if now is not None else time.time()
    with _cache_lock:
        expired = [k for k, (exp, _) in _cache.items() if ts >= exp]
        for k in expired:
            del _cache[k]
        while len(_cache) >= MAX_CACHE_ENTRIES:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (ts + _cache_ttl_seconds(), response)


# ---------------------------------------------------------------------------
# Rate limiting (in-process, per IP + global — same pattern as auth login)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_ask_attempts: Dict[str, deque] = {}  # ip -> deque[timestamps]
_ask_attempts_global: deque = deque()


def max_per_minute() -> int:
    return int(os.getenv("ASK_MAX_PER_MINUTE", str(DEFAULT_MAX_PER_MINUTE)))


def max_per_minute_global() -> int:
    return int(os.getenv("ASK_MAX_PER_MINUTE_GLOBAL", str(DEFAULT_MAX_PER_MINUTE_GLOBAL)))


def allow_ask(ip: str, now: Optional[float] = None) -> bool:
    """Record one model-call attempt for `ip`; False when a window is full.

    Cache hits never reach this function — replaying the demo stays free.
    """
    ts = now if now is not None else time.time()
    with _rate_lock:
        window = _ask_attempts.setdefault(ip, deque())
        while window and ts - window[0] > RATE_WINDOW_SECONDS:
            window.popleft()
        while _ask_attempts_global and ts - _ask_attempts_global[0] > RATE_WINDOW_SECONDS:
            _ask_attempts_global.popleft()
        if len(window) >= max_per_minute():
            return False
        if len(_ask_attempts_global) >= max_per_minute_global():
            return False
        window.append(ts)
        _ask_attempts_global.append(ts)
        return True


def reset_ask_state() -> None:
    """Test helper: clear the cache and both rate-limit windows."""
    with _cache_lock:
        _cache.clear()
    with _rate_lock:
        _ask_attempts.clear()
        _ask_attempts_global.clear()


# ---------------------------------------------------------------------------
# Claude client (the only network touchpoint — tests monkeypatch _get_client)
# ---------------------------------------------------------------------------

_client = None
_client_lock = threading.Lock()


def _get_client():
    """Lazily build the singleton Anthropic client (key comes from the env)."""
    global _client
    with _client_lock:
        if _client is None:
            import anthropic

            _client = anthropic.Anthropic(
                timeout=float(os.getenv("ASK_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
                max_retries=1,
            )
        return _client


def call_model(system: str, user: str) -> ModelReply:
    """One non-streaming Messages API call; provider failures → AskUpstreamError.

    Error messages are deliberately terse and stack-free — they travel to the
    public demo UI as the 502 detail.
    """
    import anthropic

    request_kwargs = {
        "model": os.getenv("ASK_MODEL", DEFAULT_MODEL),
        "max_tokens": int(os.getenv("ASK_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    temperature = os.getenv("ASK_TEMPERATURE", DEFAULT_TEMPERATURE).strip().lower()
    if temperature not in ("", "none"):
        request_kwargs["temperature"] = float(temperature)

    try:
        message = _get_client().messages.create(**request_kwargs)
    except anthropic.AuthenticationError:
        raise AskUpstreamError("The model provider rejected this deployment's API key.")
    except anthropic.RateLimitError:
        raise AskUpstreamError(
            "The model provider is rate-limiting this deployment; try again shortly."
        )
    except anthropic.APITimeoutError:
        raise AskUpstreamError("The model provider timed out; try again.")
    except anthropic.APIConnectionError:
        raise AskUpstreamError("Could not reach the model provider; try again.")
    except anthropic.APIStatusError as e:
        raise AskUpstreamError(f"Model provider error (HTTP {e.status_code}); try again.")

    text = "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ).strip()
    if not text:
        text = "The model returned no answer for this query."
    return ModelReply(
        text=text,
        model=message.model,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
        stop_reason=getattr(message, "stop_reason", None),
    )
