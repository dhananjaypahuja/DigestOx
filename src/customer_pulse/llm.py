"""The one door to Claude: typed requests, a privacy gate, a request-hash cache, and replay.

Every model call in Pulse goes through :func:`call`. A request is a plain dictionary, exactly
the body sent to the Messages API, so Pulse can hash it, check it, store it, and replay it:

- **The request gate** refuses a request that holds anything redaction would catch: an email
  address, a phone number, or a secret (decision 0005, gate 2). Evidence reaches the model
  only inside ``<evidence>`` blocks whose contents are escaped, so customer text can't close a
  block or open a new one.
- **The cache** keys each validated response by a hash of the complete request. A request
  seen before is answered from the cache, never sent again.
- **Replay mode** answers only from the cache and fails on a miss, so a demo re-run needs no
  key and costs nothing. It proves reproducibility, not model quality.
- **Live mode** sends a cache miss to Claude. The key comes from the environment the Anthropic
  SDK reads (``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile); Pulse never stores,
  logs, or prints it.

Model settings (decision 0012): ``claude-opus-5-5`` at ``effort: high``, adaptive thinking
(the model's only mode), structured JSON output, and no server-side fallback. A refusal or a
truncated reply stops the run; a different model never answers in its place.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from customer_pulse.clock import Clock
from customer_pulse.errors import PulseError
from customer_pulse.redact import find_raw
from customer_pulse.timewin import to_db

LIVE, REPLAY = "live", "replay"

# USD per million tokens, from Anthropic's published prices (checked 2026-09-29). Thinking
# tokens are billed, and reported, as output tokens.
PRICES_PER_MTOK = {"claude-opus-5-5": (4.00, 20.00)}


@dataclass(frozen=True)
class Settings:
    model: str
    effort: str
    max_tokens: int


@dataclass(frozen=True)
class Request:
    """One model request, before it is sent."""

    task: str
    prompt_version: str
    schema_version: str
    body: dict[str, Any]

    @property
    def sha256(self) -> str:
        identity = {
            "task": self.task,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "body": self.body,
        }
        canonical = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reply:
    """What the model returned: its JSON text and what it cost."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass(frozen=True)
class Outcome:
    data: BaseModel
    from_cache: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float
    request_sha256: str


class Transport(Protocol):
    """Sends one request body to a model. Tests use a fake; live runs use Anthropic's SDK."""

    def send(self, body: dict[str, Any]) -> Reply: ...


def build_request(
    task: str,
    prompt_version: str,
    schema_version: str,
    settings: Settings,
    system: str,
    user: str,
    schema: dict[str, Any],
) -> Request:
    body = {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {
            "effort": settings.effort,
            "format": {"type": "json_schema", "schema": schema},
        },
    }
    return Request(task, prompt_version, schema_version, body)


# Evidence blocks


def escape(text: str) -> str:
    """Escape customer text for an evidence block, so it can't close or forge a delimiter."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def evidence_block(attributes: dict[str, str | int], text: str, tag: str = "evidence") -> str:
    attrs = " ".join(f'{key}="{escape(str(value))}"' for key, value in attributes.items())
    return f"<{tag} {attrs}>\n{escape(text)}\n</{tag}>"


# The gate


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for pair in value.items() for v in pair for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def check_request(request: Request) -> None:
    """Refuse a request that holds a contact detail or a secret anywhere in its body."""
    found = sorted({kind for text in _strings(request.body) for kind in find_raw(text)})
    if found:
        raise PulseError(
            "request_gate",
            f"the {request.task} request holds unredacted {', '.join(found)}, so it wasn't sent",
            hint="this is a bug in how Pulse built the request; nothing left this machine",
        )


def check_response(response: Any, task: str) -> None:
    """Refuse generated or imported text that would put raw details in the cache."""
    found = sorted({kind for text in _strings(response) for kind in find_raw(text)})
    if found:
        raise PulseError(
            "response_gate",
            f"the {task} response holds unredacted {', '.join(found)}, so it wasn't saved",
            hint="the model or replay file returned private text; correct the source "
            "before retrying",
        )


# Calling


def call(
    conn: sqlite3.Connection,
    request: Request,
    output: type[BaseModel],
    mode: str,
    transport: Callable[[], Transport],
    clock: Clock,
    check: Callable[[Any], None] = lambda _: None,
) -> Outcome:
    """Answer ``request`` from the cache, or, in live mode, from the model.

    ``transport`` is a factory, so replay mode and cache hits never construct a client or look
    for a key. ``check`` applies the caller's own rules to a parsed answer; only an answer that
    passes is cached, so a bad answer is asked again rather than replayed forever.
    """
    check_request(request)
    sha = request.sha256
    cached = conn.execute(
        "SELECT response_json FROM llm_cache WHERE request_sha256 = ?", (sha,)
    ).fetchone()
    if cached is not None:
        data = _validate(cached[0], output, request)
        check(data)
        return Outcome(data, True, 0, 0, 0.0, sha)
    if mode != LIVE:
        raise PulseError(
            "replay_miss",
            f"no saved response for this {request.task} request, and replay mode can't call "
            "the model",
            hint="run once in live mode, or load the replay file that holds this request",
        )
    reply = transport().send(request.body)
    if reply.model != request.body["model"]:
        raise PulseError(
            "model_mismatch",
            f"the {request.task} response came from a different model, so it wasn't saved",
            hint="Pulse does not allow a fallback model (decision 0012)",
        )
    data = _validate(reply.text, output, request)
    check(data)
    conn.execute(
        "INSERT INTO llm_cache (request_sha256, task, model, effort, prompt_version, "
        "schema_version, request_json, response_json, input_tokens, output_tokens, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sha,
            request.task,
            request.body["model"],
            request.body["output_config"]["effort"],
            request.prompt_version,
            request.schema_version,
            json.dumps(request.body, sort_keys=True, ensure_ascii=False),
            data.model_dump_json(),
            reply.input_tokens,
            reply.output_tokens,
            to_db(clock.now()),
        ),
    )
    return Outcome(data, False, reply.input_tokens, reply.output_tokens, cost(reply), sha)


def _validate(text: str, output: type[BaseModel], request: Request) -> BaseModel:
    try:
        data = output.model_validate_json(text)
    except ValidationError as exc:
        raise PulseError(
            "invalid_model_output",
            f"the {request.task} response doesn't match its schema: "
            f"{exc.error_count()} problem(s), first: {exc.errors()[0]['msg']}",
            hint="nothing was saved; re-run, and report it if it repeats",
        ) from exc
    check_response(json.loads(text), request.task)
    return data


def cost(reply: Reply) -> float:
    prices = PRICES_PER_MTOK.get(reply.model)
    if prices is None:
        return 0.0
    return (reply.input_tokens * prices[0] + reply.output_tokens * prices[1]) / 1_000_000


# Live transport


class AnthropicTransport:
    """Sends requests with Anthropic's Python SDK, using the credentials it finds itself."""

    def __init__(self) -> None:
        import anthropic

        self._anthropic = anthropic
        missing = PulseError(
            "no_api_key",
            "live mode needs Anthropic credentials, and none were found",
            hint="export ANTHROPIC_API_KEY in the shell that runs pulse, or run `ant auth "
            "login`; or leave out --live to use saved responses",
        )
        try:
            self._client = anthropic.Anthropic()
        except anthropic.AnthropicError as exc:
            raise missing from exc
        # The SDK only complains at request time, so check before anything is sent.
        if all(
            getattr(self._client, a, None) is None for a in ("api_key", "auth_token", "credentials")
        ):
            raise missing

    def send(self, body: dict[str, Any]) -> Reply:
        anthropic = self._anthropic
        try:
            response = self._client.messages.create(**body)
        except anthropic.AuthenticationError as exc:
            raise PulseError(
                "no_api_key",
                "Anthropic rejected the credentials",
                hint="check ANTHROPIC_API_KEY or your `ant auth` profile",
            ) from exc
        except anthropic.APIStatusError as exc:
            raise PulseError(
                "model_error",
                f"the Messages API returned {exc.status_code}: {exc.message}",
                hint=f"request id {exc.request_id}" if getattr(exc, "request_id", None) else None,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise PulseError("model_unreachable", "couldn't reach the Messages API") from exc
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise PulseError(
                "model_refused",
                f"the model declined the request (category: {category or 'none given'})",
                hint="Pulse uses no fallback model, so the run stopped (decision 0012)",
            )
        if response.stop_reason != "end_turn":
            raise PulseError(
                "model_incomplete",
                f"the model stopped early ({response.stop_reason})",
                hint="raise llm.max_tokens, or report it if it repeats",
            )
        text = next((block.text for block in response.content if block.type == "text"), "")
        return Reply(
            text, response.usage.input_tokens, response.usage.output_tokens, response.model
        )


# Replay files


def response_sha256(response: Any) -> str:
    canonical = json.dumps(response, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def export_replay(conn: sqlite3.Connection, task: str | None = None) -> list[dict[str, Any]]:
    """The cached requests and responses, in a stable order, for a committed replay file."""
    rows = conn.execute(
        "SELECT request_sha256, task, model, effort, prompt_version, schema_version, "
        "request_json, response_json FROM llm_cache WHERE ? IS NULL OR task = ? "
        "ORDER BY task, request_sha256",
        (task, task),
    ).fetchall()
    return [
        {
            **{
                k: row[k]
                for k in (
                    "request_sha256",
                    "task",
                    "model",
                    "effort",
                    "prompt_version",
                    "schema_version",
                )
            },
            "request": json.loads(row["request_json"]),
            "response": json.loads(row["response_json"]),
            "response_sha256": response_sha256(json.loads(row["response_json"])),
        }
        for row in rows
    ]


def import_replay(conn: sqlite3.Connection, entries: list[dict[str, Any]], clock: Clock) -> int:
    """Load only intact, privacy-checked replay entries into the cache."""
    added = 0
    for entry in entries:
        request = Request(
            entry["task"], entry["prompt_version"], entry["schema_version"], entry["request"]
        )
        if request.sha256 != entry["request_sha256"]:
            raise PulseError(
                "invalid_replay_file",
                f"a {entry['task']} entry's hash doesn't match its request",
                hint="the replay file was edited; export it again",
            )
        check_request(request)
        if response_sha256(entry["response"]) != entry.get("response_sha256"):
            raise PulseError(
                "invalid_replay_file",
                f"a {request.task} entry's hash doesn't match its response",
                hint="the replay file was edited; export it again",
            )
        if (
            entry["model"] != request.body["model"]
            or entry["effort"] != request.body["output_config"]["effort"]
        ):
            raise PulseError(
                "invalid_replay_file",
                f"a {request.task} entry's model settings don't match its request",
                hint="the replay file was edited; export it again",
            )
        check_response(entry["response"], request.task)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO llm_cache (request_sha256, task, model, effort, "
            "prompt_version, schema_version, request_json, response_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.sha256,
                request.task,
                entry["model"],
                entry["effort"],
                request.prompt_version,
                request.schema_version,
                json.dumps(request.body, sort_keys=True, ensure_ascii=False),
                json.dumps(entry["response"], sort_keys=True, ensure_ascii=False),
                to_db(clock.now()),
            ),
        )
        added += cursor.rowcount
    return added
