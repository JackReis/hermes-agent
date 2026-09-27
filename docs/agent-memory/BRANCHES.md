# Profile routes and provider branches

How a gateway seat picks a memory plane, then how each adapter keys its records. Read `HARVEST.md` for the lifecycle. Read `SIMPLIFICATIONS.md` before simplifying a branch.

## Route 0 — bind the profile

```text
incoming seat
  ├─ -p / --profile <id>           → HERMES_HOME = profiles/<id>
  ├─ HERMES_HOME parent is "profiles" → keep that home
  ├─ <hermes-root>/active_profile  → that name, unless "default"
  └─ else                          → ~/.hermes  (name "default")
```

Everything below reads that home. A second profile is a second process, not a second provider inside this one.

`agent_identity` = `get_active_profile_name()` → `default` | `<profile id>` | `custom`.
`agent_workspace` = `"hermes"` (literal in `agent/agent_init.py`).

## Route 1 — curated files (always considered)

```text
skip_memory?
  yes → no MEMORY.md, no USER.md, no external provider
  no  → memory.memory_enabled or memory.user_profile_enabled?
          yes → MemoryStore at $HERMES_HOME/memories/
          no  → curated plane off
```

Targets are `memory` (MEMORY.md, agent notes) and `user` (USER.md, user model). Limits default to 2200 and 1375 characters. Writes that fail the § round-trip are refused.

## Route 2 — one external provider

```text
memory.provider empty or whitespace?
  yes → stop (curated plane only)
  no  → load_memory_provider(name)
          missing / import error / is_available() false → manager dropped, log only
          available → add_provider (second external name is rejected)
            enabled_toolsets is None or contains "memory"?
              yes → inject that provider's tool schemas
              no  → provider runs for prefetch/sync, tools stay hidden
```

`is_available()` false is a clean miss. Do not retry with a guessed name.

## Route 3 — who is allowed to write

```text
caller
  ├─ primary chat / gateway turn     → agent_context "primary", writes allowed
  ├─ cron scheduler                  → skip_memory, platform "cron"
  ├─ delegate_task child             → skip_memory; parent on_delegation only
  ├─ batch_runner                    → skip_memory
  ├─ background review fork          → skip_memory
  ├─ curator                         → skip_memory
  └─ gateway compress / hygiene agent → skip_memory
```

Session id rotation without teardown (`/resume`, `/branch`, `/reset`, `/new`, compression) calls `on_session_switch`. `reset=True` flushes per-session buffers. It does not switch profiles.

## Route 4 — gateway session key

Built by `build_session_key()`. Profile is not a component.

```text
chat_type dm
  ├─ chat_id + thread_id → agent:main:{platform}:dm:{chat_id}:{thread_id}
  ├─ chat_id             → agent:main:{platform}:dm:{chat_id}
  ├─ thread_id only      → agent:main:{platform}:dm:{thread_id}
  └─ neither             → agent:main:{platform}:dm

group / channel / other
  agent:main:{platform}:{chat_type}[:{chat_id}][:{thread_id}][:{user}]
  user appended when group_sessions_per_user and (no thread, or thread_sessions_per_user)
```

`agent:main` is a fixed prefix. It does not mean the default profile.

## Adapter branches

Only the active provider's branch is live. Tool names below are the schemas that provider registers. Calling another provider's tool name returns "No memory provider handles tool …".

### honcho

Config: `$HERMES_HOME/honcho.json` plus API key. CLI: `hermes honcho` when this is the active provider.

Init abort: `agent_context` in `{cron, flush}` or `platform == cron` sets `_cron_skipped` and returns before any session exists.

Session name (`HonchoClientConfig.resolve_session_name`), first match wins:

1. Manual cwd override in the sessions map.
2. Hermes session title (`/title`), sanitized; optional `{peer_name}-` prefix.
3. `gateway_session_key` with non-alphanumerics turned into `-`, then length-capped with a hash suffix.
4. `sessionStrategy=per-session` and a session id → that id (optional peer prefix).
5. `per-repo` → git root directory name.
6. `per-directory` (and `per-session` with no session id) → cwd basename.
7. `global` → workspace id.

Gateway keys always take step 3, so CLI strategies do not merge chats. `per-session` skips MEMORY.md/USER.md/SOUL.md migration because every run would upload a fresh copy.

Recall mode `tools` defers session creation until the first tool call unless `init_on_session_start`. `context` and `hybrid` create the session and prewarm at init.

Peers: `user_id` and `user_id_alt` become runtime user peer names. AI peer comes from `honcho.json`, not from SOUL.md. SOUL.md is persona content.

Tools: `honcho_profile`, `honcho_search`, `honcho_reasoning`, `honcho_context`, `honcho_conclude`.

### hindsight

Config: `$HERMES_HOME/hindsight/config.json`. Modes: `cloud`, `local_embedded` (legacy alias `local`), `local_external`. `local_embedded` with a missing runtime sets mode `disabled` and returns.

Bank id: `bank_id_template` if set, else static `bank_id` / `banks.hermes.bankId`, else `"hermes"`. Template placeholders, each sanitized to alphanumerics plus `-` and `_`:

| Placeholder | Source |
| --- | --- |
| `{profile}` | `agent_identity` |
| `{workspace}` | `agent_workspace` (`"hermes"`) |
| `{platform}` | `platform` |
| `{user}` | gateway `user_id` |
| `{session}` | session id |

Empty pieces collapse. An invalid template falls back to the static bank id. Without a template, banks are **not** split by profile or user.

`document_id` is `{session_id}-{YYYYmmdd_HHMMSS_ffffff}` per process, so `/resume` does not overwrite the previous retain. Session id stays in tags.

`memory_mode`: `context`, `tools`, or `hybrid` (default). `recall_budget` / `budget` must be a known budget or it becomes `mid`.

Tools: `hindsight_retain`, `hindsight_recall`, `hindsight_reflect`.

### mem0

Config: `$HERMES_HOME/mem0.json`. `user_id` = gateway `user_id` if present, else config/env, else `hermes-user`. `agent_id` = config, else `hermes`. It does **not** read `agent_identity`.

Search and list filter on `user_id` only (cross-session for that user). Adds also send `agent_id`. A circuit breaker pauses calls after consecutive failures. Empty prefetch means the breaker is open, the search missed, or the background thread has not finished — not "this user has no history."

Tools: `mem0_profile`, `mem0_search`, `mem0_conclude`.

### supermemory

Config: `$HERMES_HOME/supermemory.json`. Requires `SUPERMEMORY_API_KEY` or the provider stays inactive.

Container tag: `SUPERMEMORY_CONTAINER_TAG` if set, else `container_tag` from the JSON, with `{identity}` replaced by `agent_identity` (default `"default"` when the kwarg is missing). Optional `custom_containers` add more tags. Writes are off when `agent_context` is `cron`, `flush`, or `subagent`.

Tools: `supermemory_store`, `supermemory_search`, `supermemory_forget`, `supermemory_profile`.

### retaindb

Requires `RETAINDB_API_KEY`. Local queue: `$HERMES_HOME/retaindb_queue.db`.

Project: `RETAINDB_PROJECT` if set; else `hermes-<basename(hermes_home)>` when that basename is not empty and not `.hermes`; else `"default"`. The default profile (`~/.hermes`) therefore uses project `default`. A named profile `coder` uses `hermes-coder` unless the env var overrides it.

`user_id` from kwargs, else `"default"`. `agent_id` from kwargs `agent_id`, else `"hermes"`. Agent init does not pass `agent_id`, so the default holds unless the caller sets it. SOUL.md at `$HERMES_HOME/SOUL.md` is seeded in the background as that agent id. It is persona text, not a second profile route.

Tools: `retaindb_profile`, `retaindb_search`, `retaindb_context`, `retaindb_remember`, `retaindb_forget`, `retaindb_upload_file`, `retaindb_list_files`, `retaindb_read_file`, `retaindb_ingest_file`, `retaindb_delete_file`.

### openviking

Endpoint, account, user, and agent come from the environment (`OPENVIKING_ENDPOINT`, `OPENVIKING_ACCOUNT`, `OPENVIKING_USER`, `OPENVIKING_AGENT`), defaulting account/user to `default` and agent to `hermes`. Gateway `user_id` is not applied. Per-chat isolation is not automatic. An unreachable endpoint or missing `httpx` clears the client and the prompt block goes quiet.

Tools: `viking_search`, `viking_read`, `viking_browse`, `viking_remember`, `viking_add_resource`.

### holographic

Local SQLite. Default file `$HERMES_HOME/memory_store.db`. `db_path` may contain `$HERMES_HOME` / `${HERMES_HOME}`, expanded from the active home. One database per home, not per gateway user. Trust starts at `default_trust` (0.5 in the plugin README) and moves through `fact_feedback`. FTS5 candidates are reranked and multiplied by trust.

Tools: `fact_store`, `fact_feedback`.

### byterover

Working tree is `$HERMES_HOME/byterover`, created at init. The `brv` CLI must be on `PATH` (`is_available` checks the binary, not the network). Optional `BRV_API_KEY` is for cloud sync. `prefetch` runs `brv query` synchronously; short queries return empty. `sync_turn` runs `brv curate` on a daemon thread for substantive turns.

Tools: `brv_query`, `brv_curate`, `brv_status`.

## Branch the seat must not collapse

| If you assume… | The code does… |
| --- | --- |
| One memory store for every profile | Each profile has its own home, files, and `memory.provider` |
| The session key names the profile | The key is platform/chat/user. The profile is the process |
| `agent:main` is the default profile | It is a constant prefix |
| Mem0, OpenViking, and Holographic split by `agent_identity` automatically | Only Hindsight templates, Supermemory `{identity}`, and RetainDB's basename rule do |
| A child agent writes the parent's bank | The child is `skip_memory`. The parent may observe via `on_delegation` |
| An inactive provider's CLI exists | `discover_plugin_cli_commands()` returns nothing unless that name is `memory.provider` |
