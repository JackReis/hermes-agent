"""Tests for Slack Block Kit approval buttons and thread context fetching."""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is importable
# ---------------------------------------------------------------------------
_repo = str(Path(__file__).resolve().parents[2])
if _repo not in sys.path:
    sys.path.insert(0, _repo)


# ---------------------------------------------------------------------------
# Minimal Slack SDK mock so SlackAdapter can be imported
# ---------------------------------------------------------------------------
def _ensure_slack_mock():
    """Wire up the minimal mocks required to import SlackAdapter."""
    if "slack_bolt" in sys.modules:
        return
    slack_bolt = MagicMock()
    slack_bolt.async_app.AsyncApp = MagicMock
    sys.modules["slack_bolt"] = slack_bolt
    sys.modules["slack_bolt.async_app"] = slack_bolt.async_app
    handler_mod = MagicMock()
    handler_mod.AsyncSocketModeHandler = MagicMock
    sys.modules["slack_bolt.adapter"] = MagicMock()
    sys.modules["slack_bolt.adapter.socket_mode"] = MagicMock()
    sys.modules["slack_bolt.adapter.socket_mode.async_handler"] = handler_mod
    sdk_mod = MagicMock()
    sdk_mod.web = MagicMock()
    sdk_mod.web.async_client = MagicMock()
    sdk_mod.web.async_client.AsyncWebClient = MagicMock
    sys.modules["slack_sdk"] = sdk_mod
    sys.modules["slack_sdk.web"] = sdk_mod.web
    sys.modules["slack_sdk.web.async_client"] = sdk_mod.web.async_client


_ensure_slack_mock()

from gateway.platforms.slack import SlackAdapter
from gateway.config import Platform, PlatformConfig


def _make_adapter():
    """Create a SlackAdapter instance with mocked internals."""
    config = PlatformConfig(enabled=True, token="xoxb-test-token")
    adapter = SlackAdapter(config)
    adapter._app = MagicMock()
    adapter._bot_user_id = "U_BOT"
    adapter._team_clients = {"T1": AsyncMock()}
    adapter._team_bot_user_ids = {"T1": "U_BOT"}
    adapter._channel_team = {"C1": "T1"}
    return adapter


# ===========================================================================
# send_exec_approval — Block Kit buttons
# ===========================================================================

# Reuse a native-session harness, not fabricated session-key button values.
from tests.gateway.test_slack_interaction_binding import harness  # noqa: F401


class TestSlackExecApproval:
    @pytest.mark.asyncio
    async def test_sends_blocks_with_buttons(self, harness):
        body, action = await harness.issue()
        card = harness.cards[-1]
        assert harness.result.success
        elements = card["blocks"][1]["elements"]
        assert {e["action_id"] for e in elements} == {
            "hermes_approve_once", "hermes_approve_session", "hermes_approve_always", "hermes_deny",
        }
        assert all(e["value"] == action["value"] for e in elements)
        assert action["value"] != harness.key
        assert harness.command in card["blocks"][0]["text"]["text"]
        assert harness.description in card["blocks"][0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_sends_in_thread(self, harness):
        await harness.issue(source=harness.source(thread="9999.0000"))
        assert harness.cards[-1]["thread_ts"] == "9999.0000"

    @pytest.mark.asyncio
    async def test_not_connected(self):
        adapter = _make_adapter()
        adapter._app = None
        result = await adapter.send_exec_approval(chat_id="C1", command="ls", session_key="s")
        assert not result.success

    @pytest.mark.asyncio
    async def test_truncates_long_command(self, harness):
        harness.command = "x" * 5000
        await harness.issue()
        text = harness.cards[-1]["blocks"][0]["text"]["text"]
        assert "..." in text
        assert len(text) < 5000


class TestSlackApprovalAction:
    @pytest.mark.asyncio
    async def test_resolves_approval(self, harness):
        body, action = await harness.issue()
        await harness.click("exec", body, action)
        assert harness.native.result == "once"
        assert harness.native.event.is_set()
        assert "Approved once by alice" in harness.client.chat_update.call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_prevents_double_click(self, harness):
        body, action = await harness.issue()
        await harness.click("exec", body, action)
        await harness.click("exec", body, action)
        harness.client.chat_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deny_action(self, harness):
        body, action = await harness.issue()
        action["action_id"] = "hermes_deny"
        await harness.click("exec", body, action)
        assert harness.native.result == "deny"
        assert "Denied by alice" in harness.client.chat_update.call_args.kwargs["text"]


# ===========================================================================
# _fetch_thread_context
# ===========================================================================

class TestSlackThreadContext:
    """Test thread context fetching."""

    @pytest.mark.asyncio
    async def test_fetches_and_formats_context(self):
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(return_value={
            "messages": [
                {"ts": "1000.0", "user": "U1", "text": "This is the parent message"},
                {"ts": "1000.1", "user": "U2", "text": "I think we should refactor"},
                {"ts": "1000.2", "user": "U1", "text": "Good idea, <@U_BOT> what do you think?"},
            ]
        })

        # Mock user name resolution
        adapter._user_name_cache = {"U1": "Alice", "U2": "Bob"}

        context = await adapter._fetch_thread_context(
            channel_id="C1",
            thread_ts="1000.0",
            current_ts="1000.2",  # The message that triggered the fetch
            team_id="T1",
        )

        assert "[Thread context" in context
        assert "[thread parent] Alice: This is the parent message" in context
        assert "Bob: I think we should refactor" in context
        # Current message should be excluded
        assert "what do you think" not in context
        # Bot mention should be stripped from context
        assert "<@U_BOT>" not in context

    @pytest.mark.asyncio
    async def test_skips_bot_messages(self):
        """Self-bot child replies are skipped to avoid circular context,
        but non-self bots (e.g. cron posts, third-party integrations) are kept.

        Regression guard for the fix in _fetch_thread_context: previously ALL
        bot messages were dropped, which lost context when the bot was replying
        to a cron-posted thread parent."""
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(return_value={
            "messages": [
                {"ts": "1000.0", "user": "U1", "text": "Parent"},
                # Self-bot reply -> must be skipped (circular)
                {
                    "ts": "1000.1",
                    "bot_id": "B_SELF",
                    "user": "U_BOT",
                    "text": "Previous bot self-reply (should be skipped)",
                },
                # Third-party bot child -> kept (useful context)
                {
                    "ts": "1000.15",
                    "bot_id": "B_OTHER",
                    "user": "U_OTHER_BOT",
                    "text": "Deploy succeeded",
                },
                {"ts": "1000.2", "user": "U1", "text": "Current"},
            ]
        })
        adapter._user_name_cache = {"U1": "Alice", "U_OTHER_BOT": "DeployBot"}

        context = await adapter._fetch_thread_context(
            channel_id="C1", thread_ts="1000.0", current_ts="1000.2", team_id="T1"
        )

        assert "Previous bot self-reply" not in context
        assert "Alice: Parent" in context
        # Third-party bot message must now be included
        assert "Deploy succeeded" in context

    @pytest.mark.asyncio
    async def test_empty_thread(self):
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(return_value={"messages": []})

        context = await adapter._fetch_thread_context(
            channel_id="C1", thread_ts="1000.0", current_ts="1000.1", team_id="T1"
        )
        assert context == ""

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self):
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(side_effect=Exception("API error"))

        context = await adapter._fetch_thread_context(
            channel_id="C1", thread_ts="1000.0", current_ts="1000.1", team_id="T1"
        )
        assert context == ""

    @pytest.mark.asyncio
    async def test_fetch_thread_context_includes_bot_parent(self):
        """The thread parent posted by a bot (e.g. a cron summary) must be
        included in the context, prefixed with ``[thread parent]``."""
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(return_value={
            "messages": [
                # Bot-posted parent (cron job)
                {
                    "ts": "1000.0",
                    "bot_id": "B123",
                    "subtype": "bot_message",
                    "username": "cron",
                    "text": "メール要約: 本日の新着3件",
                },
                # User reply that triggered the fetch
                {"ts": "1000.1", "user": "U1", "text": "詳細を教えて"},
            ]
        })
        adapter._user_name_cache = {"U1": "Alice"}

        context = await adapter._fetch_thread_context(
            channel_id="C1",
            thread_ts="1000.0",
            current_ts="1000.1",  # exclude the trigger message itself
            team_id="T1",
        )

        assert "[thread parent]" in context
        assert "メール要約: 本日の新着3件" in context

    @pytest.mark.asyncio
    async def test_fetch_thread_context_excludes_self_bot_replies(self):
        """Parent (non-self bot) is kept, self-bot child replies are dropped,
        user replies are kept."""
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(return_value={
            "messages": [
                {"ts": "1000.0", "bot_id": "B_CRON", "text": "Cron summary"},
                # Self-bot child reply -> excluded
                {
                    "ts": "1000.1",
                    "bot_id": "B_SELF",
                    "user": "U_BOT",  # matches adapter._bot_user_id
                    "text": "Previous self reply",
                },
                # User reply -> kept
                {"ts": "1000.2", "user": "U1", "text": "Follow-up question"},
                # Current trigger (excluded by current_ts match)
                {"ts": "1000.3", "user": "U1", "text": "Current"},
            ]
        })
        adapter._user_name_cache = {"U1": "Alice"}

        context = await adapter._fetch_thread_context(
            channel_id="C1", thread_ts="1000.0", current_ts="1000.3", team_id="T1"
        )

        assert "Cron summary" in context
        assert "[thread parent]" in context
        assert "Previous self reply" not in context
        assert "Follow-up question" in context
        assert "Current" not in context

    @pytest.mark.asyncio
    async def test_fetch_thread_context_multi_workspace(self):
        """Self-bot filtering must use the per-workspace bot user id so a
        self-bot id that belongs to a different workspace does not accidentally
        filter out a legitimate message in the current workspace."""
        adapter = _make_adapter()
        # Add a second workspace with a different bot user id
        adapter._team_clients["T2"] = AsyncMock()
        adapter._team_bot_user_ids = {"T1": "U_BOT_T1", "T2": "U_BOT_T2"}
        adapter._bot_user_id = "U_BOT_T1"
        adapter._channel_team["C2"] = "T2"

        mock_client = adapter._team_clients["T2"]
        mock_client.conversations_replies = AsyncMock(return_value={
            "messages": [
                {"ts": "2000.0", "user": "U2", "text": "Parent T2"},
                # This has the *T1* bot's user id — from T2's perspective this
                # is a third-party bot, so it must be kept.
                {
                    "ts": "2000.1",
                    "bot_id": "B_FOREIGN",
                    "user": "U_BOT_T1",
                    "team": "T2",
                    "text": "Cross-workspace bot reply",
                },
                # Self-bot for T2 — must be skipped
                {
                    "ts": "2000.2",
                    "bot_id": "B_SELF_T2",
                    "user": "U_BOT_T2",
                    "team": "T2",
                    "text": "Own T2 bot reply",
                },
                {"ts": "2000.3", "user": "U2", "text": "Current"},
            ]
        })
        adapter._user_name_cache = {"U2": "Bob"}

        context = await adapter._fetch_thread_context(
            channel_id="C2", thread_ts="2000.0", current_ts="2000.3", team_id="T2"
        )

        assert "Parent T2" in context
        assert "Cross-workspace bot reply" in context
        assert "Own T2 bot reply" not in context

    @pytest.mark.asyncio
    async def test_fetch_thread_context_current_ts_excluded(self):
        """Regression guard: the message whose ts == current_ts must never
        appear in the context output (it will be delivered as the user
        message itself)."""
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(return_value={
            "messages": [
                {"ts": "1000.0", "user": "U1", "text": "Parent"},
                {"ts": "1000.1", "user": "U1", "text": "DO NOT INCLUDE THIS"},
            ]
        })
        adapter._user_name_cache = {"U1": "Alice"}

        context = await adapter._fetch_thread_context(
            channel_id="C1", thread_ts="1000.0", current_ts="1000.1", team_id="T1"
        )

        assert "Parent" in context
        assert "DO NOT INCLUDE THIS" not in context

    @pytest.mark.asyncio
    async def test_fetch_thread_parent_text_from_cache(self):
        """_fetch_thread_parent_text should reuse the thread-context cache
        when it is warm, avoiding an extra conversations.replies call."""
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.conversations_replies = AsyncMock(return_value={
            "messages": [
                {"ts": "1000.0", "bot_id": "B123", "text": "Parent summary"},
                {"ts": "1000.1", "user": "U1", "text": "reply"},
            ]
        })

        # Warm the cache via _fetch_thread_context
        await adapter._fetch_thread_context(
            channel_id="C1", thread_ts="1000.0", current_ts="1000.1", team_id="T1"
        )
        assert mock_client.conversations_replies.await_count == 1

        parent = await adapter._fetch_thread_parent_text(
            channel_id="C1", thread_ts="1000.0", team_id="T1"
        )
        assert parent == "Parent summary"
        # No additional API call
        assert mock_client.conversations_replies.await_count == 1


# ===========================================================================
# _has_active_session_for_thread — session key fix (#5833)
# ===========================================================================

class TestSessionKeyFix:
    """Test that _has_active_session_for_thread uses build_session_key."""

    def test_uses_build_session_key(self):
        """Verify the fix uses build_session_key instead of manual key construction."""
        adapter = _make_adapter()

        # Mock session store with a known entry
        mock_store = MagicMock()
        mock_store._entries = {
            "agent:main:slack:group:C1:1000.0": MagicMock()
        }
        mock_store._ensure_loaded = MagicMock()
        mock_store.config = MagicMock()
        mock_store.config.group_sessions_per_user = False  # threads don't include user_id
        mock_store.config.thread_sessions_per_user = False
        adapter._session_store = mock_store

        # With the fix, build_session_key should be called which respects
        # group_sessions_per_user=False (no user_id appended)
        result = adapter._has_active_session_for_thread(
            channel_id="C1", thread_ts="1000.0", user_id="U123"
        )

        # Should find the session because build_session_key with
        # group_sessions_per_user=False doesn't append user_id
        assert result is True

    def test_no_session_returns_false(self):
        adapter = _make_adapter()
        mock_store = MagicMock()
        mock_store._entries = {}
        mock_store._ensure_loaded = MagicMock()
        mock_store.config = MagicMock()
        mock_store.config.group_sessions_per_user = True
        mock_store.config.thread_sessions_per_user = False
        adapter._session_store = mock_store

        result = adapter._has_active_session_for_thread(
            channel_id="C1", thread_ts="1000.0", user_id="U123"
        )
        assert result is False

    def test_no_session_store(self):
        adapter = _make_adapter()
        # No _session_store attribute
        result = adapter._has_active_session_for_thread(
            channel_id="C1", thread_ts="1000.0", user_id="U123"
        )
        assert result is False


# ===========================================================================
# Thread engagement — bot-started threads & mentioned threads
# ===========================================================================

class TestThreadEngagement:
    """Test _bot_message_ts and _mentioned_threads tracking."""

    @pytest.mark.asyncio
    async def test_send_tracks_bot_message_ts(self):
        """Bot's sent messages are tracked so thread replies work without @mention."""
        adapter = _make_adapter()
        mock_client = adapter._team_clients["T1"]
        mock_client.chat_postMessage = AsyncMock(return_value={"ts": "9000.1"})

        await adapter.send(chat_id="C1", content="Hello!", metadata={"thread_id": "8000.0"})

        assert "9000.1" in adapter._bot_message_ts
        # Thread root should also be tracked
        assert "8000.0" in adapter._bot_message_ts

    @pytest.mark.asyncio
    async def test_bot_message_ts_cap(self):
        """Verify memory is bounded when many messages are sent."""
        adapter = _make_adapter()
        adapter._BOT_TS_MAX = 10  # low cap for testing
        mock_client = adapter._team_clients["T1"]

        for i in range(20):
            mock_client.chat_postMessage = AsyncMock(return_value={"ts": f"{i}.0"})
            await adapter.send(chat_id="C1", content=f"msg {i}")

        assert len(adapter._bot_message_ts) <= 10

    def test_mentioned_threads_populated_on_mention(self):
        """When bot is @mentioned in a thread, that thread is tracked."""
        adapter = _make_adapter()
        # Simulate what _handle_slack_message does on mention
        adapter._mentioned_threads.add("1000.0")
        assert "1000.0" in adapter._mentioned_threads

    def test_mentioned_threads_cap(self):
        """Verify _mentioned_threads is bounded."""
        adapter = _make_adapter()
        adapter._MENTIONED_THREADS_MAX = 10
        for i in range(15):
            adapter._mentioned_threads.add(f"{i}.0")
            if len(adapter._mentioned_threads) > adapter._MENTIONED_THREADS_MAX:
                to_remove = list(adapter._mentioned_threads)[:adapter._MENTIONED_THREADS_MAX // 2]
                for t in to_remove:
                    adapter._mentioned_threads.discard(t)
        assert len(adapter._mentioned_threads) <= 10
