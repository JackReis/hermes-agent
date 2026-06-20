"""Tests for the Mission Control BYOM aggregate endpoint."""

from __future__ import annotations

import pytest


def _client():
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN

    client = TestClient(app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return client


def test_mission_control_byom_requires_dashboard_session_token():
    from starlette.testclient import TestClient

    from hermes_cli.dashboard_auth.public_paths import PUBLIC_API_PATHS
    from hermes_cli.web_server import app

    assert "/api/mission-control/byom" not in PUBLIC_API_PATHS

    response = TestClient(app).get("/api/mission-control/byom")

    assert response.status_code == 401


def test_mission_control_byom_payload_includes_fleet_sources(tmp_path, monkeypatch, _isolate_hermes_home):
    import hermes_cli.web_server as web_server

    vault = tmp_path / "vault"
    okf_pattern = vault / "okf/fleet/patterns/byom-agent-fleet-mission-control.md"
    okf_index = vault / "okf/fleet/index.md"
    okf_openskills = vault / "okf/fleet/tools/openskills-core-infrastructure.md"
    okf_openskills_catalog = vault / "okf/fleet/tools/openskills-catalog.md"
    smoke_dir = tmp_path / "smoke"
    skill_root = tmp_path / "skills/openskills"
    profile_log_dir = tmp_path / "memory-profile-logs"

    okf_pattern.parent.mkdir(parents=True, exist_ok=True)
    okf_index.parent.mkdir(parents=True, exist_ok=True)
    okf_openskills.parent.mkdir(parents=True, exist_ok=True)
    smoke_dir.mkdir(parents=True)
    profile_log_dir.mkdir(parents=True)

    okf_pattern.write_text(
        """---
title: BYOM Agent Fleet Mission Control
status: active
---

# BYOM Agent Fleet Mission Control

## Latest AI Exec Circle Inputs
- Codex subscription is being used alongside minimax and z.ai.
- OpenRouter multi model option looks interesting.

## Blueprint Commitments
- Own the box.
- Orchestrator plus executors plus heartbeat.
""",
        encoding="utf-8",
    )
    okf_index.write_text("# Fleet OKF\n\n- BYOM Agent Fleet Mission Control\n", encoding="utf-8")
    okf_openskills.write_text(
        """---
title: OpenSkills Core Infrastructure
source_url: https://unlock-ai.natebjones.com/open-skills/core-infrastructure
---

# OpenSkills Core Infrastructure
""",
        encoding="utf-8",
    )
    okf_openskills_catalog.write_text(
        """---
title: Open Skills Catalog
source_url: https://unlock-ai.natebjones.com/open-skills
---

# Open Skills Catalog

Catalog size from live readback: 31 skills across 7 categories.

## Core Infrastructure

| Skill | Purpose |
| --- | --- |
| Image Generation Gateway | Shared image generation/editing primitive. |
| Current-Information Search | Real-time/current research primitive. |

## Research & Thinking

| Skill | Purpose |
| --- | --- |
| Brain Dump Processor | Splits messy notes. |
""",
        encoding="utf-8",
    )
    (smoke_dir / "image-generation-gateway.txt").write_text("ok: generated image\n", encoding="utf-8")
    (skill_root / "image-generation-gateway").mkdir(parents=True)
    (skill_root / "image-generation-gateway/SKILL.md").write_text("# Image generation\n", encoding="utf-8")
    (profile_log_dir / "memory-honcho-dev.log").write_text(
        """starting honcho
{"profile":"memory-honcho-dev","provider":"honcho-dev","role":"real-honcho-dev-provider","status":"degraded","proof":"write","proof_id":"honcho-proof","detail":"Connection refused","transition_only":false,"not_honcho_dev_proof":false,"ts":"2026-06-20T04:15:53Z"}
""",
        encoding="utf-8",
    )
    (profile_log_dir / "memory-hindsight.log").write_text(
        """{"profile":"memory-hindsight","provider":"hindsight","role":"retained-experience-memory","status":"ok","proof":"write-readback","proof_id":"hindsight-proof","detail":"Hindsight write/readback succeeded","transition_only":false,"not_honcho_dev_proof":false,"ts":"2026-06-20T04:15:54Z"}
""",
        encoding="utf-8",
    )
    (profile_log_dir / "memory-cortex-mirror.log").write_text(
        """{"profile":"memory-cortex-mirror","provider":"cortex-mirror","role":"transition-non-hermes-mirror","status":"ok","proof":"health-readback","proof_id":"cortex-proof","detail":"Cortex health is not Honcho.dev proof.","transition_only":true,"not_honcho_dev_proof":true,"ts":"2026-06-20T04:16:17Z"}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(web_server, "_MISSION_CONTROL_VAULT", vault, raising=False)
    monkeypatch.setattr(web_server, "_OKF_INDEX", okf_index, raising=False)
    monkeypatch.setattr(web_server, "_OKF_BYOM", okf_pattern, raising=False)
    monkeypatch.setattr(web_server, "_OKF_OPENSKILLS", okf_openskills, raising=False)
    monkeypatch.setattr(web_server, "_OKF_OPENSKILLS_CATALOG", okf_openskills_catalog, raising=False)
    monkeypatch.setattr(web_server, "_OPENSKILLS_SMOKE_DIR", smoke_dir, raising=False)
    monkeypatch.setattr(web_server, "_OPENSKILLS_SKILL_ROOT", skill_root, raising=False)
    monkeypatch.setattr(web_server, "_MEMORY_PROFILE_LOG_DIR", profile_log_dir, raising=False)
    monkeypatch.setattr(
        web_server,
        "_mission_control_contextforge_health",
        lambda: {"ok": True, "status": "healthy", "url": "http://127.0.0.1:8090/health", "details": {"service": "contextforge"}},
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_contextforge_registry",
        lambda: {
            "ok": True,
            "source": "http://127.0.0.1:8090",
            "gateway": {
                "title": "ContextForge",
                "version": "1.0.3",
                "role": "IBM ContextForge gateway/registry/proxy for MCP, A2A, and REST/gRPC APIs",
            },
            "counts": {"tools": 10, "resources": 50, "gateways": 2, "servers": 2},
            "samples": {
                "gateways": [{"name": "Bifrost Fleet Bridge", "enabled": True, "reachable": True}],
                "servers": [{"name": "fleet-local-registry", "enabled": True}],
                "resources": [{"name": "skill-resource-pp-linear", "enabled": True}],
            },
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_local_turn_sync_health",
        lambda: {"ok": True, "planes": [{"name": "OBn", "ok": True}, {"name": "Hindsight", "ok": True}]},
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_honcho_health",
        lambda: {
            "ok": True,
            "status": "configured",
            "label": "Honcho.dev memory provider",
            "kind": "native-hermes-memory-provider",
            "configured": True,
            "enabled": True,
            "has_api_key": True,
            "has_base_url": False,
            "connection_tested": False,
            "disambiguation": "This is the real Hermes Honcho provider, not the local Cortex/Honcho clone.",
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_cortex_honcho_clone_health",
        lambda: {
            "ok": True,
            "status": "healthy",
            "url": "http://127.0.0.1:8002/api/v1/health",
            "label": "Cortex/Honcho clone",
            "kind": "local-cortex-honcho-clone",
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_native_memory",
        lambda honcho_health, local_turn_sync: {
            "configured": ["hindsight", "holographic", "honcho"],
            "providers": [
                {"id": "hindsight", "label": "Hindsight", "configured": True, "ok": True},
                {"id": "holographic", "label": "Holographic Memory", "configured": True, "ok": True},
                {"id": "honcho", "label": "Honcho", "configured": True, "ok": honcho_health["ok"]},
            ],
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_tailscale_status",
        lambda: {
            "ok": True,
            "source": "tailscale status --json",
            "self": {
                "HostName": "olivier",
                "DNSName": "olivier.tailnet.ts.net.",
                "TailscaleIPs": ["100.64.0.1"],
                "Online": True,
                "LastSeen": "0001-01-01T00:00:00Z",
            },
            "peers": [
                {
                    "HostName": "Aegis",
                    "DNSName": "aegis.tailnet.ts.net.",
                    "TailscaleIPs": ["100.84.253.97"],
                    "Online": False,
                    "LastSeen": "2026-06-19T15:30:15.1Z",
                }
            ],
        },
        raising=False,
    )

    response = _client().get("/api/mission-control/byom")

    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_at"]
    assert payload["contextforge"]["ok"] is True
    assert payload["contextforge_registry"]["ok"] is True
    assert payload["contextforge_registry"]["gateway"]["version"] == "1.0.3"
    assert payload["contextforge_registry"]["gateway"]["role"] == "IBM ContextForge gateway/registry/proxy for MCP, A2A, and REST/gRPC APIs"
    assert payload["contextforge_registry"]["counts"] == {"tools": 10, "resources": 50, "gateways": 2, "servers": 2}
    assert payload["contextforge_registry"]["samples"]["gateways"] == [
        {"name": "Bifrost Fleet Bridge", "enabled": True, "reachable": True}
    ]
    assert payload["local_turn_sync"]["ok"] is True
    assert [item["id"] for item in payload["sources"]] == ["okf-index", "okf-byom", "okf-openskills"]
    assert payload["sources"][1]["title"] == "BYOM Agent Fleet Mission Control"
    assert payload["sources"][2]["source_url"] == "https://unlock-ai.natebjones.com/open-skills/core-infrastructure"
    assert payload["openskills_catalog"]["source_url"] == "https://unlock-ai.natebjones.com/open-skills"
    assert payload["openskills_catalog"]["skill_count"] == 31
    assert payload["openskills_catalog"]["category_count"] == 7
    assert payload["openskills_catalog"]["categories"][:2] == [
        {"name": "Core Infrastructure", "skill_count": 2},
        {"name": "Research & Thinking", "skill_count": 1},
    ]
    assert "OpenRouter multi model option looks interesting." in payload["whatsapp_inputs"]["bullets"]
    assert payload["hosts"][0]["id"] == "olivier"
    host_by_id = {host["id"]: host for host in payload["hosts"]}
    assert host_by_id["olivier"]["reachability"] == {
        "source": "tailscale status --json",
        "status": "online",
        "last_seen": None,
        "address": "100.64.0.1",
        "matched_name": "olivier",
        "evidence": "self",
        "reason": None,
    }
    assert host_by_id["aegis"]["reachability"] == {
        "source": "tailscale status --json",
        "status": "unverified",
        "last_seen": "2026-06-19T15:30:15.1Z",
        "address": "100.84.253.97",
        "matched_name": "Aegis",
        "evidence": "peer",
        "reason": "tailscale-not-online",
    }
    assert host_by_id["bill"]["reachability"]["status"] == "unverified"
    assert host_by_id["bill"]["reachability"]["last_seen"] is None
    assert host_by_id["bill"]["reachability"]["reason"] == "not-found"
    assert payload["honcho"]["ok"] is True
    assert payload["honcho"]["kind"] == "native-hermes-memory-provider"
    assert payload["honcho"]["connection_tested"] is False
    assert payload["cortex_honcho_clone"]["kind"] == "local-cortex-honcho-clone"
    assert payload["native_memory"]["configured"] == ["hindsight", "holographic", "honcho"]
    assert [provider["id"] for provider in payload["native_memory"]["providers"]] == ["hindsight", "holographic", "honcho"]
    assert payload["skills"][0]["id"] == "image-generation-gateway"
    assert payload["skills"][0]["installed"] is True
    assert payload["skills"][0]["smoke_exists"] is True
    assert payload["skills"][0]["ok"] is True
    assert payload["memory_planes"] == payload["local_turn_sync"]["planes"]
    assert payload["memory_profile_console"]["ok"] is False
    assert [item["profile"] for item in payload["memory_profile_console"]["profiles"]] == [
        "memory-honcho-dev",
        "memory-hindsight",
        "memory-cortex-mirror",
    ]
    profile_by_id = {item["profile"]: item for item in payload["memory_profile_console"]["profiles"]}
    assert profile_by_id["memory-hindsight"]["status"] == "ok"
    assert profile_by_id["memory-honcho-dev"]["status"] == "degraded"
    assert profile_by_id["memory-cortex-mirror"]["transition_only"] is True
    assert profile_by_id["memory-cortex-mirror"]["not_honcho_dev_proof"] is True


def test_mission_control_byom_degrades_when_sources_or_planes_are_missing(tmp_path, monkeypatch, _isolate_hermes_home):
    import hermes_cli.web_server as web_server

    vault = tmp_path / "missing-vault"
    monkeypatch.setattr(web_server, "_MISSION_CONTROL_VAULT", vault, raising=False)
    monkeypatch.setattr(web_server, "_OKF_INDEX", vault / "okf/fleet/index.md", raising=False)
    monkeypatch.setattr(web_server, "_OKF_BYOM", vault / "okf/fleet/patterns/byom-agent-fleet-mission-control.md", raising=False)
    monkeypatch.setattr(web_server, "_OKF_OPENSKILLS", vault / "okf/fleet/tools/openskills-core-infrastructure.md", raising=False)
    monkeypatch.setattr(web_server, "_OKF_OPENSKILLS_CATALOG", vault / "okf/fleet/tools/openskills-catalog.md", raising=False)
    monkeypatch.setattr(web_server, "_OPENSKILLS_SMOKE_DIR", tmp_path / "no-smoke", raising=False)
    monkeypatch.setattr(web_server, "_OPENSKILLS_SKILL_ROOT", tmp_path / "no-skills", raising=False)
    monkeypatch.setattr(web_server, "_MEMORY_PROFILE_LOG_DIR", tmp_path / "no-profile-logs", raising=False)
    monkeypatch.setattr(
        web_server,
        "_mission_control_contextforge_health",
        lambda: {"ok": False, "status": "unreachable", "url": "http://127.0.0.1:8090/health", "error": "connection refused"},
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_contextforge_registry",
        lambda: {
            "ok": False,
            "source": "http://127.0.0.1:8090",
            "error": "registry unavailable",
            "counts": {"tools": 0, "resources": 0, "gateways": 0, "servers": 0},
            "samples": {"gateways": [], "servers": [], "resources": []},
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_local_turn_sync_health",
        lambda: {"ok": False, "planes": [], "exit_code": 1, "error": "health failed"},
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_honcho_health",
        lambda: {
            "ok": False,
            "status": "not-configured",
            "label": "Honcho.dev memory provider",
            "kind": "native-hermes-memory-provider",
            "configured": False,
            "enabled": False,
            "has_api_key": False,
            "has_base_url": False,
            "connection_tested": False,
            "disambiguation": "This is the real Hermes Honcho provider, not the local Cortex/Honcho clone.",
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_cortex_honcho_clone_health",
        lambda: {
            "ok": False,
            "status": "unreachable",
            "url": "http://127.0.0.1:8002/api/v1/health",
            "error": "connection refused",
            "label": "Cortex/Honcho clone",
            "kind": "local-cortex-honcho-clone",
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_native_memory",
        lambda honcho_health, local_turn_sync: {
            "configured": ["hindsight", "holographic", "honcho"],
            "providers": [
                {"id": "hindsight", "label": "Hindsight", "configured": True, "ok": False},
                {"id": "holographic", "label": "Holographic Memory", "configured": True, "ok": False},
                {"id": "honcho", "label": "Honcho", "configured": True, "ok": honcho_health["ok"]},
            ],
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_server,
        "_mission_control_tailscale_status",
        lambda: {"ok": False, "source": "tailscale status --json", "error": "tailscale unavailable"},
        raising=False,
    )

    response = _client().get("/api/mission-control/byom")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contextforge"]["ok"] is False
    assert payload["contextforge_registry"]["ok"] is False
    assert payload["contextforge_registry"]["counts"] == {"tools": 0, "resources": 0, "gateways": 0, "servers": 0}
    assert payload["honcho"]["ok"] is False
    assert any(provider["id"] == "honcho" and provider["ok"] is False for provider in payload["native_memory"]["providers"])
    assert payload["local_turn_sync"]["ok"] is False
    assert payload["memory_planes"] == []
    assert payload["memory_profile_console"]["ok"] is False
    assert payload["memory_profile_console"]["profiles"] == []
    assert all(host["reachability"]["status"] == "unverified" for host in payload["hosts"])
    assert all(host["reachability"]["source"] == "tailscale status --json" for host in payload["hosts"])
    assert payload["openskills_catalog"]["exists"] is False
    assert payload["openskills_catalog"]["skill_count"] == 0
    assert payload["openskills_catalog"]["category_count"] == 0
    assert all(source["exists"] is False for source in payload["sources"])
    assert all(skill["ok"] is False for skill in payload["skills"])
    assert any("ContextForge" in caveat for caveat in payload["caveats"])
    assert any("ContextForge registry" in caveat for caveat in payload["caveats"])
    assert any("Honcho" in caveat for caveat in payload["caveats"])
    assert any("local-turn-sync" in caveat for caveat in payload["caveats"])
