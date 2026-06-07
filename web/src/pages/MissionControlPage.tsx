import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Database,
  Globe2,
  MessageSquare,
  Network,
  Radio,
  RotateCw,
  Server,
  ShieldCheck,
  Terminal,
  Workflow,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api } from "@/lib/api";
import type {
  MissionControlForestResponse,
  MissionControlNode,
  MissionControlState,
  PlatformStatus,
  StatusResponse,
} from "@/lib/api";
import { isoTimeAgo } from "@/lib/utils";

type Surface = {
  name: string;
  role: string;
  href: string;
  state: "primary" | "evidence" | "legacy";
};

type SinewHealth = {
  ok?: boolean;
  status?: string;
  error?: string;
  message_count?: number;
  timestamp?: string;
};

const SURFACES: Surface[] = [
  {
    name: "Hermes Mission Control",
    role: "Primary cockpit for sessions, gateway state, fleet channels, and operator action.",
    href: "/mission-control",
    state: "primary",
  },
  {
    name: "Olympus",
    role: "Deprecated projection aggregator. Keep as secondary evidence while migration finishes.",
    href: "http://127.0.0.1:3020",
    state: "legacy",
  },
  {
    name: "Fleet Dashboard / Sinew",
    role: "Legacy-but-live Sinew and service-health evidence surface.",
    href: "http://127.0.0.1:8081",
    state: "evidence",
  },
];

const SINEW_HEALTH_PATH = "/sinew/api/sinew";
const SINEW_HEALTH_TIMEOUT_MS = 5000;

const PLATFORM_PRIORITY = [
  "telegram",
  "mattermost",
  "matrix",
  "slack",
  "discord",
];

const CHANNEL_PRIORITY = ["Matrix", "Telegram", "Mattermost", "Slack"];

function statusTone(state: string): "success" | "warning" | "destructive" | "outline" {
  if (state === "connected") return "success";
  if (state === "fatal") return "destructive";
  if (state === "disconnected") return "warning";
  return "outline";
}

function stateLabel(state: string): string {
  if (state === "connected") return "connected";
  if (state === "fatal") return "attention";
  if (state === "disconnected") return "offline";
  return state || "unknown";
}

function forestTone(state: MissionControlState | string): "success" | "warning" | "destructive" | "outline" {
  if (state === "live" || state === "fresh") return "success";
  if (state === "down") return "destructive";
  if (state === "degraded" || state === "stale" || state === "missing") return "warning";
  return "outline";
}

function StateBadge({ state }: { state: MissionControlState | string }) {
  return <Badge tone={forestTone(state)}>{state || "unknown"}</Badge>;
}

function sortPlatforms(
  gateway_platforms: Record<string, PlatformStatus>,
): [string, PlatformStatus][] {
  return Object.entries(gateway_platforms).sort(([a], [b]) => {
    const ai = PLATFORM_PRIORITY.indexOf(a);
    const bi = PLATFORM_PRIORITY.indexOf(b);
    if (ai >= 0 || bi >= 0) return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
    return a.localeCompare(b);
  });
}

function FleetReadiness({ status }: { status: StatusResponse }) {
  const platforms = sortPlatforms(status.gateway_platforms);
  const connected = platforms.filter(([, info]) => info.state === "connected").length;
  const fatal = platforms.filter(([, info]) => info.state === "fatal").length;
  const gatewayReady = status.gateway_running && status.gateway_state !== "fatal";
  const readiness = gatewayReady && fatal === 0 ? "aligned" : "needs attention";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {gatewayReady ? (
            <CheckCircle2 className="h-5 w-5 text-success" />
          ) : (
            <AlertTriangle className="h-5 w-5 text-warning" />
          )}
          <CardTitle className="text-base">Fleet readiness</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-3xl font-semibold tracking-normal">{readiness}</p>
            <p className="text-sm text-muted-foreground">
              Hermes is the cockpit. Daily note, handoffs, and OB1 remain the ledger.
            </p>
          </div>
          <Badge tone={gatewayReady ? "success" : "warning"}>
            gateway {status.gateway_running ? "running" : "stopped"}
          </Badge>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="border border-border p-3">
            <div className="text-2xl font-semibold">{status.active_sessions}</div>
            <div className="text-xs text-muted-foreground">active sessions</div>
          </div>
          <div className="border border-border p-3">
            <div className="text-2xl font-semibold">{connected}/{platforms.length}</div>
            <div className="text-xs text-muted-foreground">channels connected</div>
          </div>
          <div className="border border-border p-3">
            <div className="text-2xl font-semibold">{fatal}</div>
            <div className="text-xs text-muted-foreground">fatal channels</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function PlatformGrid({ status }: { status: StatusResponse }) {
  const platforms = sortPlatforms(status.gateway_platforms);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Radio className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Coordination channels</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {platforms.map(([name, info]) => (
          <div key={name} className="border border-border p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium capitalize">{name}</div>
                <div className="text-xs text-muted-foreground">
                  {info.updated_at ? isoTimeAgo(info.updated_at) : "no timestamp"}
                </div>
              </div>
              <Badge tone={statusTone(info.state)}>{stateLabel(info.state)}</Badge>
            </div>
            {info.error_message && (
              <p className="mt-2 text-xs text-destructive">{info.error_message}</p>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function InfrastructureMap({ forest }: { forest: MissionControlForestResponse }) {
  const nodesById = new Map(forest.infrastructure.nodes.map((node) => [node.id, node]));
  const orderedIds = [
    "orbstack",
    "docker_socket",
    "rbitr_compose",
    "conduit",
    "matrix_relay",
    "sinew",
  ];
  const nodes = orderedIds
    .map((id) => nodesById.get(id))
    .filter((node): node is MissionControlNode => Boolean(node));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Workflow className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Infrastructure map</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">{forest.summary.primary_issue}</p>
            <p className="text-xs text-muted-foreground">
              {forest.summary.unhealthy_count} checks need attention
            </p>
          </div>
          <StateBadge state={forest.summary.state} />
        </div>
        <div className="grid gap-2">
          {nodes.map((node) => (
            <div key={node.id} className="flex items-start justify-between gap-3 border border-border p-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{node.name}</span>
                  {node.owner && <span className="text-xs text-muted-foreground">{node.owner}</span>}
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">{node.detail || node.role}</p>
              </div>
              <StateBadge state={node.state} />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ChannelRolesCard({ forest }: { forest: MissionControlForestResponse }) {
  const channels = [...forest.channels].sort((a, b) => {
    const ai = CHANNEL_PRIORITY.indexOf(a.name);
    const bi = CHANNEL_PRIORITY.indexOf(b.name);
    if (ai >= 0 || bi >= 0) return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
    return a.name.localeCompare(b.name);
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Network className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Transport roles</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {channels.map((channel) => (
          <div key={channel.id} className="border border-border p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{channel.name}</div>
                <div className="text-xs text-muted-foreground">{channel.canonicality}</div>
              </div>
              <StateBadge state={channel.state} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{channel.detail}</p>
            <p className="mt-1 text-xs text-muted-foreground">{channel.risk}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function RemoteAccessCard({ forest }: { forest: MissionControlForestResponse }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Globe2 className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Remote access</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {forest.remote_access.map((entry) => (
          <div key={entry.id} className="flex items-start justify-between gap-3 border border-border p-3">
            <div className="min-w-0">
              <div className="text-sm font-medium">{entry.name}</div>
              <div className="truncate text-xs text-muted-foreground">{entry.url}</div>
              {entry.detail && <div className="mt-1 text-xs text-muted-foreground">{entry.detail}</div>}
            </div>
            <StateBadge state={entry.state} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function AgentLanesCard({ forest }: { forest: MissionControlForestResponse }) {
  const lanes = forest.agent_lanes.agent_work_map.length
    ? forest.agent_lanes.agent_work_map
    : forest.agent_lanes.tmux_panes;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Agent lanes</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {lanes.slice(0, 8).map((lane, index) => (
          <div
            key={`${lane.pane || lane.peer || lane.role}-${index}`}
            className="flex items-start justify-between gap-3 border border-border p-3"
          >
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">
                {lane.peer || lane.role || lane.title || "unknown lane"}
              </div>
              <div className="truncate text-xs text-muted-foreground">{lane.pane || lane.command}</div>
            </div>
            <Badge tone={lane.status === "online" ? "success" : "outline"}>
              {lane.status || lane.visibility || "visible"}
            </Badge>
          </div>
        ))}
        {lanes.length === 0 && (
          <p className="text-sm text-muted-foreground">No live lane export found.</p>
        )}
      </CardContent>
    </Card>
  );
}

function ContextFreshnessCard({ forest }: { forest: MissionControlForestResponse }) {
  const feed = forest.context.live_surface_feed;
  const latest = forest.context.latest_pointer;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Context freshness</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex items-start justify-between gap-3 border border-border p-3">
          <div>
            <div className="text-sm font-medium">Live surface export</div>
            <div className="text-xs text-muted-foreground">
              {typeof feed.age_seconds === "number" ? `${feed.age_seconds}s old` : feed.detail || "not found"}
            </div>
          </div>
          <StateBadge state={feed.state} />
        </div>
        <div className="border border-border p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium">Latest handoff pointer</span>
            <Badge tone={latest.Status === "stale" ? "warning" : "outline"}>
              {latest.Status || "unknown"}
            </Badge>
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {latest.Latest || "no latest pointer in export"}
          </p>
        </div>
        <div className="border border-border p-3">
          <div className="text-sm font-medium">Pending actions</div>
          <div className="mt-1 text-2xl font-semibold">
            {forest.context.pending_actions.length}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function OwnershipRulesCard({ forest }: { forest: MissionControlForestResponse }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Ownership rules</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {forest.ownership.map((rule) => (
          <div key={rule.owner} className="border border-border p-3">
            <div className="text-sm font-medium">{rule.owner}</div>
            <div className="mt-1 text-xs text-muted-foreground">{rule.owns}</div>
            <div className="mt-1 text-xs text-muted-foreground">{rule.boundary}</div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function SurfaceMap() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Server className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Surface map</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {SURFACES.map((surface) => (
          <a
            key={surface.name}
            href={surface.href}
            className="group flex items-start justify-between gap-4 border border-border p-3 transition-colors hover:bg-accent/40"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{surface.name}</span>
                <Badge
                  tone={
                    surface.state === "primary"
                      ? "success"
                      : surface.state === "legacy"
                        ? "warning"
                        : "outline"
                  }
                >
                  {surface.state}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{surface.role}</p>
            </div>
            <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground" />
          </a>
        ))}
      </CardContent>
    </Card>
  );
}

function ProjectionHealth() {
  const [sinew, setSinew] = useState<SinewHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadSinew = useCallback(() => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      controller.abort("Sinew check timed out");
    }, SINEW_HEALTH_TIMEOUT_MS);

    return fetch(SINEW_HEALTH_PATH, {
      credentials: "omit",
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
        return res.json() as Promise<SinewHealth>;
      })
      .then((payload) => {
        setSinew(payload);
        setError(null);
      })
      .catch((err) => {
        setSinew(null);
        setError(controller.signal.aborted ? "Sinew check timed out" : String(err));
      })
      .finally(() => {
        window.clearTimeout(timeoutId);
        setLoading(false);
      });
  }, []);

  const refresh = () => {
    setLoading(true);
    void loadSinew();
  };

  useEffect(() => {
    void loadSinew();
  }, [loadSinew]);

  const healthy = Boolean(sinew?.ok);
  const degraded = !loading && !healthy;
  const detail = error || sinew?.error || sinew?.status || "waiting for Sinew";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {healthy ? (
            <CheckCircle2 className="h-5 w-5 text-success" />
          ) : (
            <AlertTriangle className="h-5 w-5 text-warning" />
          )}
          <CardTitle className="text-base">Projection health</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium">
              Mission Control absorbs the useful Olympus projections instead of
              reviving Olympus as the cockpit.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Sinew remains evidence-only and is checked through the fleet proxy.
            </p>
          </div>
          <Button size="sm" outlined onClick={refresh} disabled={loading}>
            {loading ? <Spinner className="mr-2 h-4 w-4" /> : <RotateCw className="mr-2 h-4 w-4" />}
            Check
          </Button>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <div className="border border-border p-3">
            <div className="text-xs text-muted-foreground">Sinew state</div>
            <div className="mt-1 flex items-center gap-2">
              <Badge tone={healthy ? "success" : degraded ? "warning" : "outline"}>
                {loading ? "checking" : healthy ? "live" : "degraded"}
              </Badge>
              <span className="truncate text-xs text-muted-foreground">{detail}</span>
            </div>
          </div>
          <div className="border border-border p-3">
            <div className="text-xs text-muted-foreground">messages</div>
            <div className="mt-1 text-xl font-semibold">
              {typeof sinew?.message_count === "number" ? sinew.message_count : "—"}
            </div>
          </div>
          <a
            href="http://127.0.0.1:8081"
            className="group border border-border p-3 transition-colors hover:bg-accent/40"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">legacy evidence</span>
              <ArrowUpRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground" />
            </div>
            <div className="mt-1 text-sm font-medium">Fleet Dashboard / Sinew</div>
          </a>
        </div>
      </CardContent>
    </Card>
  );
}

function OperatorLoop() {
  const actions = [
    {
      to: "/sessions",
      icon: MessageSquare,
      label: "Inspect sessions",
      detail: "Read active and recent Hermes sessions before assigning work.",
    },
    {
      to: "/chat",
      icon: Terminal,
      label: "Open operator chat",
      detail: "Route orchestration through Hermes instead of resurrecting dashboard-only flows.",
    },
    {
      to: "/cron",
      icon: Clock,
      label: "Review ceremonies",
      detail: "Check paused and scheduled jobs without silently enabling them.",
    },
    {
      to: "/system",
      icon: Activity,
      label: "Gateway controls",
      detail: "Restart or inspect gateway state only when live evidence says it is needed.",
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Operator loop</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <Link
              key={action.to}
              to={action.to}
              className="flex gap-3 border border-border p-3 transition-colors hover:bg-accent/40"
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <span>
                <span className="block text-sm font-medium">{action.label}</span>
                <span className="block text-xs text-muted-foreground">{action.detail}</span>
              </span>
            </Link>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default function MissionControlPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [forest, setForest] = useState<MissionControlForestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forestError, setForestError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(() => {
    return Promise.allSettled([
      api.getStatus(),
      api.getMissionControlForest(),
    ])
      .then(([statusResult, forestResult]) => {
        if (statusResult.status === "fulfilled") {
          setStatus(statusResult.value);
          setError(null);
        } else {
          setError(String(statusResult.reason));
        }

        if (forestResult.status === "fulfilled") {
          setForest(forestResult.value);
          setForestError(null);
        } else {
          setForestError(String(forestResult.reason));
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  const refresh = () => {
    setLoading(true);
    void fetchStatus();
  };

  const lastUpdate = status?.gateway_updated_at
    ? isoTimeAgo(status.gateway_updated_at)
    : "no gateway timestamp";
  const forestUpdate = forest?.generated_at
    ? isoTimeAgo(forest.generated_at)
    : "no forest timestamp";

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
      <header className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs uppercase text-muted-foreground">
            <Activity className="h-4 w-4" />
            Fleet coordination
          </div>
          <h1 className="text-3xl font-semibold tracking-normal">Mission Control</h1>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            Hermes is the cockpit for active fleet coordination. Olympus is deprecated as
            the primary command surface and stays linked here only as read-only evidence
            during the migration.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            Gateway {lastUpdate} · Forest {forestUpdate}
          </span>
          <Button size="sm" outlined onClick={refresh} disabled={loading}>
            {loading ? <Spinner className="mr-2 h-4 w-4" /> : <RotateCw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </header>

      {error && (
        <div className="border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          Mission Control could not load Hermes status: {error}
        </div>
      )}

      {forestError && (
        <div className="border border-warning/40 bg-warning/10 p-3 text-sm text-warning">
          Mission Control could not load forest state: {forestError}
        </div>
      )}

      {loading && !status ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner className="h-4 w-4" />
          Loading fleet status…
        </div>
      ) : status ? (
        <>
          <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
            <FleetReadiness status={status} />
            <SurfaceMap />
          </section>
          {forest && (
            <>
              <section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                <InfrastructureMap forest={forest} />
                <RemoteAccessCard forest={forest} />
              </section>
              <section className="grid gap-5 xl:grid-cols-[1fr_1fr]">
                <ChannelRolesCard forest={forest} />
                <AgentLanesCard forest={forest} />
              </section>
              <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
                <ContextFreshnessCard forest={forest} />
                <OwnershipRulesCard forest={forest} />
              </section>
            </>
          )}
          <ProjectionHealth />
          <section className="grid gap-5 xl:grid-cols-[1fr_1fr]">
            <PlatformGrid status={status} />
            <OperatorLoop />
          </section>
        </>
      ) : null}
    </div>
  );
}
