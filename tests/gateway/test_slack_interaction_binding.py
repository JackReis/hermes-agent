"""Exercise real adapter entrypoints and native waiters with mocked Slack I/O."""

import asyncio
import copy
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.platforms.slack import SlackAdapter
from gateway.session import SessionStore
from tools import approval, slash_confirm


class InteractionHarness:
    native: Any

    def __init__(self, tmp_path):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner.pairing_store = MagicMock()
        runner.pairing_store.is_approved.return_value = False
        self.auth_runner = runner
        self._authorize = runner._is_user_authorized
        self.store = SessionStore(tmp_path / "sessions", GatewayConfig())
        self.adapter = SlackAdapter(PlatformConfig(enabled=True, token="test-only"))
        self.adapter._app = MagicMock()
        self.client = AsyncMock()
        self.adapter._team_clients = {"T1": self.client}
        self.adapter._channel_team = {"C1": "T1", "D1": "T1"}
        self.adapter._bot_user_id = "UBOT"
        self.adapter.set_session_store(self.store)
        self.adapter.set_message_handler(self._handle_message)
        self.adapter._running = True
        self.calls = []
        self.cards = []
        self.command = "rm important"
        self.description = "dangerous deletion"
        self.kind = "exec"
        self.command_from_event = False
        self.thread_bridge = False
        self.issue_lock = asyncio.Lock()

    def _is_user_authorized(self, source):
        return self._authorize(source)

    def source(self, chat="C1", thread="100.1", user="U1", team="T1"):
        return self.adapter.build_source(
            chat_id=chat, chat_type="dm" if chat.startswith("D") else "group",
            user_id=user, thread_id=thread, guild_id=team,
        )

    async def _handle_message(self, event):
        async with self.issue_lock:
            if self.command_from_event:
                self.command = event.text
            self.entry = self.store.get_or_create_session(event.source)
            self.key = self.entry.session_key
            metadata = {"thread_id": event.source.thread_id} if event.source.thread_id else None
            if self.kind == "exec":
                native = approval._ApprovalEntry({
                    "command": self.command, "description": self.description,
                    "pattern_keys": ["delete"],
                })
                with approval._lock:
                    approval._gateway_queues.setdefault(self.key, []).append(native)
                self.native = native
                coro = self.adapter.send_exec_approval(
                    event.source.chat_id, self.command, self.key, self.description, metadata,
                )
            else:
                async def handler(choice):
                    self.calls.append(choice)
                    return "Confirmed"
                slash_confirm.register(self.key, "confirm-1", "reload-mcp", handler)
                self.native = slash_confirm.get_pending(self.key)
                coro = self.adapter.send_slash_confirm(
                    event.source.chat_id, "Confirm", "Reload?", self.key, "confirm-1", metadata,
                )
            self.client.chat_postMessage.return_value = {"ts": f"200.{len(self.cards) + 1}"}
            if self.thread_bridge:
                loop = asyncio.get_running_loop()
                result = await asyncio.to_thread(
                    lambda: asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=5),
                )
            else:
                result = await coro
            self.result = result
            if result.success:
                payload = copy.deepcopy(self.client.chat_postMessage.call_args.kwargs)
                self.cards.append(payload)

    async def issue(self, kind="exec", source=None):
        self.kind = kind
        source = source or self.source()
        await self.adapter.handle_message(MessageEvent(
            text="request", message_type=MessageType.TEXT, source=source,
        ))
        # The base adapter spawns its handler; drain its actual owner tasks.
        tasks = list(self.adapter._session_tasks.values())
        if tasks:
            await asyncio.gather(*tasks)
        if not self.result.success:
            return None, None
        card = self.cards[-1]
        body = {
            "team": {"id": source.guild_id}, "channel": {"id": source.chat_id},
            "user": {"id": source.user_id, "name": "alice"},
            "message": {"ts": self.result.message_id, "blocks": card["blocks"]},
        }
        if source.thread_id:
            body["message"]["thread_ts"] = source.thread_id
        return body, copy.deepcopy(card["blocks"][1]["elements"][0])

    async def click(self, kind, body, action):
        ack = AsyncMock()
        handler = (self.adapter._handle_approval_action if kind == "exec"
                   else self.adapter._handle_slash_confirm_action)
        await handler(ack, body, action)
        ack.assert_awaited_once()

    def unresolved(self, kind):
        if kind == "exec":
            assert not self.native.event.is_set()
            assert self.native.result is None
        else:
            assert not self.calls
            assert slash_confirm.get_pending(self.key) is not None
        self.client.chat_update.assert_not_awaited()


@pytest.fixture
def harness(tmp_path, monkeypatch):
    for name in ("GATEWAY_ALLOW_ALL_USERS", "GATEWAY_ALLOWED_USERS",
                 "SLACK_ALLOW_ALL_USERS", "SLACK_ALLOWED_USERS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SLACK_ALLOWED_USERS", "U1,U2")
    with approval._lock:
        approval._gateway_queues.clear()
    with slash_confirm._lock:
        slash_confirm._pending.clear()
    instance = InteractionHarness(tmp_path)
    yield instance
    with approval._lock:
        approval._gateway_queues.clear()
    with slash_confirm._lock:
        slash_confirm._pending.clear()
    if instance.store._db:
        instance.store._db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
@pytest.mark.parametrize("field", ["actor", "team", "channel", "thread", "card", "token",
                                  "action", "missing_actor", "missing_team", "missing_thread",
                                  "container_channel", "container_card"])
async def test_rejects_cross_scope_callback(harness, kind, field):
    body, action = await harness.issue(kind)
    if field == "actor":
        body["user"]["id"] = "U2"  # Also allowlisted: shared thread is not shared approval.
    elif field == "team":
        body["team"]["id"] = "T2"
    elif field == "channel":
        body["channel"]["id"] = "C2"
    elif field == "thread":
        body["message"]["thread_ts"] = "999.1"
    elif field == "card":
        body["message"]["ts"] = "999.2"
    elif field == "token":
        action["value"] = harness.key + ("|confirm-1" if kind == "confirm" else "")
    elif field == "action":
        action["action_id"] = "hermes_unknown"
    elif field == "missing_actor":
        body["user"].pop("id")
    elif field == "missing_team":
        body.pop("team")
    elif field == "missing_thread":
        body["message"].pop("thread_ts")
    elif field == "container_channel":
        body["container"] = {"channel_id": "C2"}
    else:
        body["container"] = {"message_ts": "999.2"}
    await harness.click(kind, body, action)
    harness.unresolved(kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
@pytest.mark.parametrize("state", ["expired", "restart", "session", "subject", "replaced",
                                  "policy", "no_runner", "team_mapping"])
async def test_rejects_stale_request(harness, monkeypatch, kind, state):
    body, action = await harness.issue(kind)
    if state == "expired":
        for pending in harness.adapter._interactions._pending.values():
            pending.expires_at = time.monotonic() - 1
    elif state == "restart":
        harness.adapter._interactions = type(harness.adapter._interactions)()
    elif state == "session":
        harness.entry.session_id = "another-native-session"
    elif state == "subject":
        if kind == "exec":
            harness.native.data["command"] = "different command"
        else:
            slash_confirm._pending[harness.key]["command"] = "different command"
    elif state == "replaced":
        if kind == "exec":
            approval._gateway_queues[harness.key] = [approval._ApprovalEntry(dict(harness.native.data))]
        else:
            slash_confirm.register(harness.key, "confirm-1", "reload-mcp", AsyncMock())
    elif state == "policy":
        monkeypatch.setenv("SLACK_ALLOWED_USERS", "   ")
    elif state == "no_runner":
        harness.adapter.set_message_handler(AsyncMock())
    else:
        harness.adapter._channel_team["C1"] = "T2"
    await harness.click(kind, body, action)
    harness.unresolved(kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
@pytest.mark.parametrize("chat,thread", [("C1", "100.1"), ("D1", "100.1"), ("D1", None), ("C1", None)])
async def test_accepts_bound_request_once(harness, kind, chat, thread):
    body, action = await harness.issue(kind, harness.source(chat=chat, thread=thread))
    assert action["value"] != harness.key
    await asyncio.gather(harness.click(kind, body, action), harness.click(kind, body, action))
    if kind == "exec":
        assert harness.native.result == "once"
        assert harness.native.event.is_set()
    else:
        assert harness.calls == ["once"]
        assert slash_confirm.get_pending(harness.key) is None
        assert harness.client.chat_postMessage.call_args.kwargs["thread_ts"] == (thread or body["message"]["ts"])
    harness.client.chat_update.assert_awaited_once()
    update = harness.client.chat_update.call_args.kwargs
    assert update["channel"] == chat
    assert update["ts"] == body["message"]["ts"]
    assert "Approved once by alice" in update["text"]
    assert not any(block["type"] == "actions" for block in update["blocks"])


@pytest.mark.asyncio
async def test_thread_bridge_retains_initiator(harness):
    harness.thread_bridge = True
    body, action = await harness.issue()
    await harness.click("exec", body, action)
    assert harness.native.result == "once"


@pytest.mark.asyncio
async def test_out_of_order_cards_resolve_exact_waiter(harness):
    first_body, first_action = await harness.issue()
    first = harness.native
    harness.command = "rm second"
    second_body, second_action = await harness.issue()
    second = harness.native
    await harness.click("exec", second_body, second_action)
    assert second.result == "once"
    assert first.result is None
    await harness.click("exec", first_body, first_action)
    assert first.result == "once"


@pytest.mark.asyncio
async def test_old_card_cannot_resolve_replacement_after_text_approval(harness):
    body, action = await harness.issue()
    assert approval.resolve_gateway_approval(harness.key, "deny") == 1
    old = harness.native
    await harness.issue()
    await harness.click("exec", body, action)
    harness.unresolved("exec")
    assert old.result == "deny"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
async def test_swapped_valid_token_does_not_cross_session(harness, kind):
    first_body, _ = await harness.issue(kind)
    first_key = harness.key
    _, other_action = await harness.issue(kind, harness.source(thread="100.2"))
    assert harness.key != first_key
    await harness.click(kind, first_body, other_action)
    harness.unresolved(kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
async def test_update_failure_cannot_replay_decision(harness, kind):
    body, action = await harness.issue(kind)
    harness.client.chat_update.side_effect = RuntimeError("offline")
    await harness.click(kind, body, action)
    await harness.click(kind, body, action)
    if kind == "exec":
        assert harness.native.result == "once"
    else:
        assert harness.calls == ["once"]
    assert harness.client.chat_update.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
@pytest.mark.parametrize("state", ["blank_policy", "no_store", "no_runner", "no_team",
                                  "missing_actor", "suspended", "ambiguous", "unknown_delivery"])
async def test_card_creation_fails_closed(harness, monkeypatch, kind, state):
    source = harness.source()
    if state == "blank_policy":
        monkeypatch.setenv("SLACK_ALLOWED_USERS", " ")
    elif state == "no_store":
        harness.adapter.set_session_store(None)
    elif state == "no_runner":
        # Keep the actual handler, but remove the native authorization seam.
        harness._is_user_authorized = None
    elif state == "no_team":
        source.guild_id = None
    elif state == "missing_actor":
        source.user_id = None
    elif state == "suspended":
        prepare = harness.adapter._prepare_interaction
        def suspended(*args, **kwargs):
            harness.entry.suspended = True
            return prepare(*args, **kwargs)
        monkeypatch.setattr(harness.adapter, "_prepare_interaction", suspended)
    elif state == "ambiguous":
        prepare = harness.adapter._prepare_interaction
        def ambiguous(*args, **kwargs):
            if kind == "exec":
                approval._gateway_queues[harness.key].append(approval._ApprovalEntry(dict(harness.native.data)))
            else:
                slash_confirm.clear(harness.key)
            return prepare(*args, **kwargs)
        monkeypatch.setattr(harness.adapter, "_prepare_interaction", ambiguous)
    else:
        prepare = harness.adapter._prepare_interaction
        def unknown_delivery(*args, **kwargs):
            harness.client.chat_postMessage.return_value = {}
            return prepare(*args, **kwargs)
        monkeypatch.setattr(harness.adapter, "_prepare_interaction", unknown_delivery)
    await harness.issue(kind, source)
    assert not harness.result.success
    assert not harness.adapter._interactions._pending
    if state != "unknown_delivery":
        harness.client.chat_postMessage.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
async def test_no_initiator_context_cannot_create_card(harness, kind):
    body, action = await harness.issue(kind)
    harness.client.chat_postMessage.reset_mock()
    if kind == "exec":
        result = await harness.adapter.send_exec_approval("C1", harness.command, harness.key, harness.description)
    else:
        result = await harness.adapter.send_slash_confirm("C1", "Confirm", "Reload?", harness.key, "confirm-1")
    assert not result.success
    harness.client.chat_postMessage.assert_not_awaited()
    # A rejected second card does not disable the original valid request.
    await harness.click(kind, body, action)
    if kind == "exec":
        assert harness.native.result == "once"
    else:
        assert harness.calls == ["once"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
async def test_malformed_tokens_do_not_consume(harness, kind):
    body, action = await harness.issue(kind)
    for token in (None, [], {}, 42, ""):
        malformed = {**action, "value": token}
        await harness.click(kind, body, malformed)
        harness.unresolved(kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
async def test_native_request_disappeared(harness, kind):
    body, action = await harness.issue(kind)
    if kind == "exec":
        approval._gateway_queues.clear()
    else:
        slash_confirm.clear(harness.key)
    await harness.click(kind, body, action)
    assert not harness.calls
    harness.client.chat_update.assert_not_awaited()
    if kind == "exec":
        assert harness.native.result is None


@pytest.mark.asyncio
async def test_native_confirm_timeout_independent_of_card_ttl(harness):
    body, action = await harness.issue("confirm")
    native = slash_confirm._pending[harness.key]
    native["created_at"] -= 301
    # Keep the snapshot consistent to specifically exercise native expiration.
    harness.adapter._interactions._pending[action["value"]].subject["created_at"] = native["created_at"]
    await harness.click("confirm", body, action)
    harness.unresolved("confirm")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
async def test_disconnect_invalidates_card(harness, kind):
    body, action = await harness.issue(kind)
    await harness.adapter.disconnect()
    await harness.click(kind, body, action)
    harness.unresolved(kind)


@pytest.mark.asyncio
async def test_slack_status_and_native_thread_isolation_preserved(harness):
    adapter = harness.adapter
    first = harness.store.get_or_create_session(harness.source(thread="100.1"))
    second = harness.store.get_or_create_session(harness.source(thread="100.2"))
    dm = harness.store.get_or_create_session(harness.source(chat="D1", thread="100.1"))
    assert len({first.session_id, second.session_id, dm.session_id}) == 3
    assert harness.store.get_or_create_session(harness.source(user="U2")).session_id == first.session_id
    await adapter.send_typing("C1", metadata={"thread_id": "100.1"})
    assert harness.client.assistant_threads_setStatus.call_args.kwargs["thread_ts"] == "100.1"
    await adapter.stop_typing("C1", metadata={"thread_id": "100.1"})
    assert harness.client.assistant_threads_setStatus.call_args.kwargs["status"] == ""
    body, action = await harness.issue()
    await harness.click("exec", body, action)
    assert harness.client.chat_update.call_args.kwargs["ts"] == body["message"]["ts"]


@pytest.mark.asyncio
async def test_queued_shared_thread_uses_current_turn_actor(harness):
    adapter = harness.adapter
    harness.command_from_event = True
    await harness.issue_lock.acquire()
    try:
        first = MessageEvent(text="first", message_type=MessageType.TEXT, source=harness.source(user="U1"))
        queued = MessageEvent(text="second", message_type=MessageType.TEXT, source=harness.source(user="U2"))
        await adapter.handle_message(first)
        await asyncio.sleep(0)
        await adapter.handle_message(queued)
    finally:
        harness.issue_lock.release()
    while adapter._background_tasks:
        await asyncio.gather(*list(adapter._background_tasks))
    assert len(harness.cards) == 2
    bindings = list(adapter._interactions._pending.values())
    assert [binding.source.user_id for binding in bindings] == ["U1", "U2"]
    assert bindings[0].session_key == bindings[1].session_key
    assert bindings[0].token != bindings[1].token
    body = {
        "team": {"id": "T1"}, "channel": {"id": "C1"}, "user": {"id": "U1"},
        "message": {"ts": harness.result.message_id, "thread_ts": "100.1"},
    }
    action = harness.cards[-1]["blocks"][1]["elements"][0]
    await harness.click("exec", body, action)
    harness.unresolved("exec")
    body["user"]["id"] = "U2"
    await harness.click("exec", body, action)
    assert harness.native.result == "once"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["exec", "confirm"])
@pytest.mark.parametrize("policy", ["global_allowlist", "pairing"])
async def test_uses_normal_gateway_authorization(harness, monkeypatch, kind, policy):
    monkeypatch.delenv("SLACK_ALLOWED_USERS")
    if policy == "global_allowlist":
        monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "U1")
    else:
        harness.auth_runner.pairing_store.is_approved.return_value = True
    body, action = await harness.issue(kind)
    await harness.click(kind, body, action)
    if kind == "exec":
        assert harness.native.result == "once"
    else:
        assert harness.calls == ["once"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,action_id,choice", [
    ("exec", "hermes_approve_session", "session"),
    ("exec", "hermes_approve_always", "always"),
    ("exec", "hermes_deny", "deny"),
    ("confirm", "hermes_confirm_always", "always"),
    ("confirm", "hermes_confirm_cancel", "cancel"),
])
async def test_only_native_request_receives_existing_choice(harness, kind, action_id, choice):
    body, action = await harness.issue(kind)
    action["action_id"] = action_id
    await harness.click(kind, body, action)
    if kind == "exec":
        assert harness.native.result == choice
        assert harness.key not in approval._gateway_queues
    else:
        assert harness.calls == [choice]
        assert slash_confirm.get_pending(harness.key) is None
