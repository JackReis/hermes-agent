import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  Cpu,
  Database,
  FileText,
  Network,
  RefreshCw,
  Server,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { usePageHeader } from "@/contexts/usePageHeader";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  MissionControlByomResponse,
  MissionControlContextForgeRegistry,
  MissionControlContextForgeRegistrySample,
  MissionControlHealth,
  MissionControlMemoryProfileConsole,
  MissionControlOpenSkillsCatalog,
  MissionControlPlane,
  MissionControlSkill,
  MissionControlSource,
} from "@/lib/api";
import { PluginSlot } from "@/plugins";

function formatDate(value: string | null | undefined): string {
  if (!value) return "not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(value: number | null): string {
  if (value === null) return "missing";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function HealthPill({ ok, label }: { ok: boolean; label?: string }) {
  return (
    <Badge tone={ok ? "success" : "destructive"}>
      {ok ? "ok" : label ?? "degraded"}
    </Badge>
  );
}

function ReachabilityBadge({ status }: { status: string }) {
  if (status === "online") return <Badge tone="success">online</Badge>;
  return <Badge tone="warning">{status}</Badge>;
}

function SourceRow({ source }: { source: MissionControlSource }) {
  return (
    <div className="grid gap-2 border-b border-border/60 py-3 last:border-0 md:grid-cols-[1.25fr_1fr_auto] md:items-center">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium">
            {source.title ?? source.id}
          </span>
          <HealthPill ok={source.exists} label="missing" />
        </div>
        <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
          {source.path}
        </div>
      </div>
      <div className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground/80">{source.kind}</span>
        <span className="mx-2">/</span>
        {formatDate(source.mtime)}
      </div>
      <div className="font-mono text-xs text-muted-foreground">
        {formatBytes(source.byte_size)}
      </div>
    </div>
  );
}

function SkillRow({ skill }: { skill: MissionControlSkill }) {
  return (
    <div className="grid gap-2 border-b border-border/60 py-3 last:border-0 md:grid-cols-[1fr_1fr] md:items-center">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <Wrench className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium">{skill.label}</span>
          <HealthPill ok={skill.ok} />
        </div>
        <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
          {skill.skill_path}
        </div>
      </div>
      <div className="min-w-0 text-xs text-muted-foreground">
        <div className="truncate font-mono">{skill.smoke_path}</div>
        <div className="mt-1 truncate text-foreground/80">
          {skill.smoke_line ?? "no smoke readback"}
        </div>
      </div>
    </div>
  );
}

function OpenSkillsCatalogCard({ catalog }: { catalog: MissionControlOpenSkillsCatalog }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
            <CardTitle className="truncate text-base">Open Skills catalog</CardTitle>
          </div>
          <HealthPill ok={catalog.exists} label="missing" />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded border border-border/70 px-3 py-2">
            <div className="text-xs text-muted-foreground">skills</div>
            <div className="mt-1 text-lg font-semibold">{catalog.skill_count}</div>
          </div>
          <div className="rounded border border-border/70 px-3 py-2">
            <div className="text-xs text-muted-foreground">categories</div>
            <div className="mt-1 text-lg font-semibold">{catalog.category_count}</div>
          </div>
        </div>
        {catalog.source_url && (
          <a
            className="block truncate font-mono text-xs text-primary underline-offset-4 hover:underline"
            href={catalog.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {catalog.source_url}
          </a>
        )}
        <div className="truncate font-mono text-xs text-muted-foreground">
          {catalog.path}
        </div>
        <div className="flex flex-wrap gap-2">
          {catalog.categories.slice(0, 7).map((category) => (
            <Badge key={category.name} tone="secondary">
              {category.name}: {category.skill_count}
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function planeLabel(plane: MissionControlPlane): string {
  const raw = plane.name ?? plane.id ?? plane.plane ?? "memory plane";
  return String(raw);
}

function planeDetail(plane: MissionControlPlane): string {
  const raw = plane.status ?? plane.detail ?? plane.error ?? "";
  return String(raw);
}

function HealthPanel({
  title,
  icon: Icon,
  health,
}: {
  title: string;
  icon: typeof Database;
  health: MissionControlHealth;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />
            <CardTitle className="truncate text-base">{title}</CardTitle>
          </div>
          <HealthPill ok={health.ok} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {health.url && (
          <div className="truncate font-mono text-xs text-muted-foreground">
            {health.url}
          </div>
        )}
        {health.status && (
          <div className="text-muted-foreground">
            status <span className="text-foreground">{health.status}</span>
          </div>
        )}
        {typeof health.exit_code === "number" && (
          <div className="text-muted-foreground">
            exit <span className="font-mono text-foreground">{health.exit_code}</span>
          </div>
        )}
        {health.error && (
          <div className="rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {health.error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MemoryProfileConsolePanel({ console }: { console: MissionControlMemoryProfileConsole }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Brain className="h-5 w-5 shrink-0 text-muted-foreground" />
            <CardTitle className="truncate text-base">Memory profile console</CardTitle>
          </div>
          <HealthPill ok={console.ok} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="truncate font-mono text-xs text-muted-foreground">
          {console.source}
        </div>
        {console.profiles.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {console.profiles.map((profile) => (
              <div key={profile.profile} className="rounded border border-border/70 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{profile.profile}</div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">
                      {profile.role ?? profile.provider}
                    </div>
                  </div>
                  <Badge tone={profile.status === "ok" ? "success" : "destructive"}>
                    {profile.status}
                  </Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge tone="secondary">{profile.proof ?? "proof pending"}</Badge>
                  {profile.transition_only && <Badge tone="warning">transition only</Badge>}
                  {profile.not_honcho_dev_proof && <Badge tone="warning">not Honcho.dev proof</Badge>}
                </div>
                {profile.detail && (
                  <div className="mt-3 text-xs text-muted-foreground">
                    {profile.detail}
                  </div>
                )}
                {profile.proof_id && (
                  <div className="mt-2 truncate font-mono text-xs text-muted-foreground">
                    {profile.proof_id}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">No memory profile logs reported.</div>
        )}
        {console.error && (
          <div className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-xs">
            {console.error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RegistrySampleList({
  label,
  samples,
}: {
  label: string;
  samples: MissionControlContextForgeRegistrySample[];
}) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {samples.length ? (
          samples.slice(0, 5).map((sample) => (
            <Badge
              key={`${label}-${sample.name}`}
              tone={sample.reachable === false || sample.enabled === false ? "warning" : "secondary"}
            >
              {sample.name}
            </Badge>
          ))
        ) : (
          <span className="text-xs text-muted-foreground">none reported</span>
        )}
      </div>
    </div>
  );
}

function ContextForgeRegistryPanel({
  registry,
}: {
  registry: MissionControlContextForgeRegistry;
}) {
  const counts = [
    ["tools", registry.counts.tools],
    ["resources", registry.counts.resources],
    ["gateways", registry.counts.gateways],
    ["servers", registry.counts.servers],
  ] as const;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Database className="h-5 w-5 shrink-0 text-muted-foreground" />
            <CardTitle className="truncate text-base">ContextForge registry</CardTitle>
          </div>
          <HealthPill ok={registry.ok} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">
            {registry.gateway.title ?? "ContextForge"}
            {registry.gateway.version ? ` ${registry.gateway.version}` : ""}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {registry.gateway.role ?? "MCP registry and gateway control plane"}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {counts.map(([label, value]) => (
            <div key={label} className="rounded border border-border/70 px-3 py-2">
              <div className="text-xs text-muted-foreground">{label}</div>
              <div className="mt-1 text-lg font-semibold">{value}</div>
            </div>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <RegistrySampleList label="gateways" samples={registry.samples.gateways} />
          <RegistrySampleList label="servers" samples={registry.samples.servers} />
          <RegistrySampleList label="resources" samples={registry.samples.resources} />
        </div>
        {registry.error && (
          <div className="rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {registry.error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function LoadingState() {
  return (
    <div className="flex min-h-[280px] items-center justify-center">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner />
        <span>Loading Mission Control</span>
      </div>
    </div>
  );
}

export default function MissionControlPage() {
  const [data, setData] = useState<MissionControlByomResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { setAfterTitle, setEnd } = usePageHeader();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getMissionControlByom()
      .then(setData)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useLayoutEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        {data && (
          <Badge tone={data.caveats.length ? "warning" : "success"}>
            {data.caveats.length ? `${data.caveats.length} caveats` : "clear"}
          </Badge>
        )}
        <Button
          type="button"
          ghost
          size="icon"
          className="text-muted-foreground hover:text-foreground"
          onClick={load}
          disabled={loading}
          aria-label="Refresh Mission Control"
        >
          {loading ? <Spinner /> : <RefreshCw />}
        </Button>
      </div>,
    );
    setEnd(null);
    return () => {
      setAfterTitle(null);
      setEnd(null);
    };
  }, [data, load, loading, setAfterTitle, setEnd]);

  const healthyPlanes = useMemo(
    () => data?.memory_planes.filter((plane) => plane.ok !== false).length ?? 0,
    [data],
  );

  if (loading && !data) return <LoadingState />;

  if (error && !data) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex items-center gap-2 text-destructive">
            <XCircle className="h-5 w-5" />
            <span className="text-sm">{error}</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div className="flex flex-col gap-5">
      <PluginSlot name="mission-control:top" />

      <div className="grid gap-3 md:grid-cols-4">
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Activity className="h-4 w-4" />
              generated
            </div>
            <div className="mt-2 text-sm font-medium">{formatDate(data.generated_at)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Network className="h-4 w-4" />
              hosts
            </div>
            <div className="mt-2 text-sm font-medium">{data.hosts.length} declared</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Wrench className="h-4 w-4" />
              Open Skills
            </div>
            <div className="mt-2 text-sm font-medium">
              {data.skills.filter((skill) => skill.ok).length}/{data.skills.length} ready
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Brain className="h-4 w-4" />
              memory planes
            </div>
            <div className="mt-2 text-sm font-medium">
              {healthyPlanes}/{data.memory_planes.length} healthy
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">OKF source readback</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {data.sources.map((source) => (
              <SourceRow key={source.id} source={source} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Cpu className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">BYOM fleet topology</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.hosts.map((host) => (
              <div key={host.id} className="flex items-start gap-3 border-b border-border/60 pb-3 last:border-0 last:pb-0">
                <Server className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{host.label}</span>
                    <ReachabilityBadge status={host.reachability.status} />
                    <Badge tone="secondary">{host.reachability.evidence ?? "local"}</Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{host.role}</div>
                  <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                    <div className="truncate font-mono">{host.reachability.source}</div>
                    <div className="flex flex-wrap gap-x-3 gap-y-1">
                      <span>
                        last seen <span className="text-foreground/80">{formatDate(host.reachability.last_seen)}</span>
                      </span>
                      {host.reachability.address && (
                        <span className="font-mono">{host.reachability.address}</span>
                      )}
                      {host.reachability.reason && (
                        <span>{host.reachability.reason}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Wrench className="h-5 w-5 text-muted-foreground" />
                <CardTitle className="text-base">Open Skills primitives</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {data.skills.map((skill) => (
                <SkillRow key={skill.id} skill={skill} />
              ))}
            </CardContent>
          </Card>

          <OpenSkillsCatalogCard catalog={data.openskills_catalog} />
        </div>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">AI Exec Circle inputs</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="truncate font-mono text-xs text-muted-foreground">
              {data.whatsapp_inputs.source}
            </div>
            <div className="space-y-2">
              {data.whatsapp_inputs.bullets.length ? (
                data.whatsapp_inputs.bullets.map((bullet) => (
                  <div key={bullet} className="flex gap-2 text-sm">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>{bullet}</span>
                  </div>
                ))
              ) : (
                <div className="text-sm text-muted-foreground">No WhatsApp bullets captured in OKF.</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <HealthPanel title="IBM/local ContextForge" icon={Database} health={data.contextforge} />
        <ContextForgeRegistryPanel registry={data.contextforge_registry} />
        <HealthPanel title="Honcho.dev memory provider" icon={Brain} health={data.honcho} />
        <MemoryProfileConsolePanel console={data.memory_profile_console} />
        <HealthPanel title="Local turn sync" icon={Brain} health={data.local_turn_sync} />
        <HealthPanel title="Cortex/Honcho clone transition service" icon={Database} health={data.cortex_honcho_clone} />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-base">Native Hermes memory stack</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {data.native_memory.providers.map((provider) => (
            <div key={provider.id} className="rounded border border-border/70 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{provider.label}</span>
                {provider.ok ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
                ) : (
                  <XCircle className="h-4 w-4 shrink-0 text-destructive" />
                )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge tone={provider.configured ? "success" : "warning"}>
                  {provider.configured ? "configured" : "not configured"}
                </Badge>
                <Badge tone={provider.ok ? "success" : "destructive"}>
                  {provider.ok ? "active" : "degraded"}
                </Badge>
              </div>
              <div className="mt-2 truncate text-xs text-muted-foreground">
                {provider.detail ?? "native Hermes memory provider"}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-base">Local turn-sync planes</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {data.memory_planes.length ? (
            data.memory_planes.map((plane) => (
              <div key={planeLabel(plane)} className="rounded border border-border/70 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{planeLabel(plane)}</span>
                  {plane.ok === false ? (
                    <XCircle className="h-4 w-4 shrink-0 text-destructive" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
                  )}
                </div>
                <div className="mt-2 truncate text-xs text-muted-foreground">
                  {planeDetail(plane) || "reported by local-turn-sync"}
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm text-muted-foreground">No memory planes reported.</div>
          )}
        </CardContent>
      </Card>

      {data.caveats.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">Caveats</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.caveats.map((caveat) => (
              <div
                key={caveat}
                className={cn(
                  "rounded border px-3 py-2 text-sm",
                  caveat.includes("degraded") || caveat.includes("Missing")
                    ? "border-warning/40 bg-warning/10"
                    : "border-border/70 bg-muted/20 text-muted-foreground",
                )}
              >
                {caveat}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
