"""Ephemeral card bindings; the gateway's native session and waiters own state."""

from __future__ import annotations

import copy
import secrets
import time
from dataclasses import dataclass
from typing import Any

from gateway.session import build_session_key


EXEC_CHOICES = {
    "hermes_approve_once": "once",
    "hermes_approve_session": "session",
    "hermes_approve_always": "always",
    "hermes_deny": "deny",
}
CONFIRM_CHOICES = {
    "hermes_confirm_once": "once",
    "hermes_confirm_always": "always",
    "hermes_confirm_cancel": "cancel",
}


@dataclass
class PendingInteraction:
    token: str
    kind: str
    source: Any
    team_id: str
    thread_id: str
    session_key: str
    session_id: str
    native_request: Any
    subject: Any
    expires_at: float
    card_id: str = ""


class SlackInteractions:
    TTL = 300.0
    MAX_PENDING = 1024

    def __init__(self):
        self._pending: dict[str, PendingInteraction] = {}

    def clear(self):
        self._pending.clear()

    def discard(self, token):
        self._pending.pop(token, None)

    def _prune(self):
        now = time.monotonic()
        for token, pending in list(self._pending.items()):
            if now >= pending.expires_at:
                self.discard(token)

    @staticmethod
    def _session(adapter, source, session_key):
        store = getattr(adapter, "_session_store", None)
        if store is None or source is None:
            return None
        if build_session_key(
            source,
            group_sessions_per_user=store.config.group_sessions_per_user,
            thread_sessions_per_user=store.config.thread_sessions_per_user,
        ) != session_key:
            return None
        store._ensure_loaded()
        with store._lock:
            entry = store._entries.get(session_key)
            if entry is None or entry.suspended:
                return None
            return entry.session_id

    @staticmethod
    def _authorized(adapter, source):
        runner = getattr(getattr(adapter, "_message_handler", None), "__self__", None)
        authorize = getattr(runner, "_is_user_authorized", None)
        return bool(source and source.user_id and callable(authorize)
                    and authorize(source) is True)

    def prepare(self, adapter, source, team_id, chat_id, thread_id,
                session_key, kind, command="", description="", confirm_id=""):
        self._prune()
        if (len(self._pending) >= self.MAX_PENDING or not source
                or source.chat_id != chat_id or source.platform != adapter.platform
                or not team_id or team_id not in adapter._team_clients
                or source.guild_id != team_id
                or not self._authorized(adapter, source)):
            raise ValueError("Slack interaction has no authenticated initiating context")
        session_id = self._session(adapter, source, session_key)
        if not session_id or (source.thread_id and source.thread_id != thread_id):
            raise ValueError("Slack interaction native session/thread unavailable")

        if kind == "exec":
            from tools import approval
            with approval._lock:
                candidates = [entry for entry in approval._gateway_queues.get(session_key, [])
                              if entry.data.get("command") == command
                              and entry.data.get("description") == description
                              and entry.result is None and not entry.event.is_set()]
                if len(candidates) != 1:
                    raise ValueError("Slack interaction approval subject unavailable or ambiguous")
                native = candidates[0]
                subject = copy.deepcopy(native.data)
        elif kind == "confirm":
            from tools import slash_confirm
            with slash_confirm._lock:
                native = slash_confirm._pending.get(session_key)
                if (not native or native.get("confirm_id") != confirm_id
                        or not callable(native.get("handler"))
                        or time.time() - native.get("created_at", 0) >= self.TTL):
                    raise ValueError("Slack interaction confirmation unavailable or expired")
                subject = dict(native)
        else:
            raise ValueError("Unknown Slack interaction kind")
        if any(p.native_request is native for p in self._pending.values()):
            raise ValueError("Slack interaction request already has a card")
        pending = PendingInteraction(
            secrets.token_urlsafe(32), kind, copy.copy(source), team_id, thread_id or "",
            session_key, session_id, native, subject, time.monotonic() + self.TTL,
        )
        self._pending[pending.token] = pending
        return pending

    def bind_card(self, pending, card_id):
        if not isinstance(card_id, str) or not card_id:
            self.discard(pending.token)
            raise ValueError("Slack interaction card delivery unknown")
        pending.card_id = card_id

    def consume(self, adapter, body, action, kind):
        self._prune()
        if not isinstance(body, dict) or not isinstance(action, dict):
            return None
        token = action.get("value")
        action_id = action.get("action_id")
        if not isinstance(token, str) or not isinstance(action_id, str):
            return None
        choices = EXEC_CHOICES if kind == "exec" else CONFIRM_CHOICES
        choice = choices.get(action_id)
        pending = self._pending.get(token)
        if not choice or pending is None or pending.kind != kind or not pending.card_id:
            return None
        message = body.get("message") or {}
        container = body.get("container") or {}
        if not all(isinstance(part, dict) for part in (
            message, container, body.get("user", {}), body.get("team", {}), body.get("channel", {}),
        )):
            return None
        user_id = (body.get("user") or {}).get("id")
        if user_id != pending.source.user_id:
            return None
        if ((body.get("team") or {}).get("id") != pending.team_id
                or (body.get("channel") or {}).get("id") != pending.source.chat_id
                or message.get("ts") != pending.card_id
                or (message.get("thread_ts") or "") != pending.thread_id
                or (container.get("message_ts", pending.card_id) != pending.card_id)
                or (container.get("channel_id", pending.source.chat_id) != pending.source.chat_id)
                or adapter._channel_team.get(pending.source.chat_id) != pending.team_id
                or pending.team_id not in adapter._team_clients):
            return None
        try:
            authorized = (self._authorized(adapter, pending.source)
                          and self._session(adapter, pending.source, pending.session_key) == pending.session_id)
        except Exception:
            authorized = False
        if not authorized:
            self.discard(pending.token)
            return None
        # No await between checking the card and consuming the native waiter.
        # The FIFO-only public exec resolver cannot safely target a parallel request.
        if kind == "exec":
            from tools import approval
            with approval._lock:
                queue = approval._gateway_queues.get(pending.session_key, [])
                native = pending.native_request
                if (native not in queue or native.data != pending.subject
                        or native.result is not None or native.event.is_set()):
                    self.discard(pending.token)
                    return None
                queue.remove(native)
                if not queue:
                    approval._gateway_queues.pop(pending.session_key, None)
                native.result = choice
                native.event.set()
        else:
            from tools import slash_confirm
            with slash_confirm._lock:
                native = slash_confirm._pending.get(pending.session_key)
                if (native is None or native is not pending.native_request or native != pending.subject
                        or time.time() - native.get("created_at", 0) >= self.TTL):
                    self.discard(pending.token)
                    return None
                slash_confirm._pending.pop(pending.session_key)
        self.discard(pending.token)
        return pending, choice
