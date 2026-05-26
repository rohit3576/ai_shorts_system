import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  BarChart3,
  Bot,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clapperboard,
  Download,
  Eye,
  Film,
  Flame,
  Gauge,
  Globe2,
  Brain,
  DollarSign,
  TrendingUp,
  Lightbulb,
  Target,
  Database,
  LayoutDashboard,
  Loader2,
  MonitorDot,
  Play,
  Radio,
  RefreshCw,
  Rocket,
  Search,
  Settings,
  Sparkles,
  Terminal,
  UploadCloud,
  Video,
  Wand2,
  Zap,
} from "lucide-react";
import {
  Chart,
  CategoryScale,
  LineController,
  BarController,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Filler,
  Legend,
} from "chart.js";
import "./styles.css";

Chart.register(
  CategoryScale,
  LineController,
  BarController,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Filler,
  Legend
);

const pageFromServer = window.DASHBOARD_PAGE || "review";
const initialPayload = window.DASHBOARD_BOOTSTRAP || {};

const navItems = [
  { id: "sources", href: "/sources", label: "Sources", icon: Globe2 },
  { id: "generate", href: "/generate", label: "Generate", icon: Zap },
  { id: "review", href: "/review", label: "Review Queue", icon: Clapperboard },
  { id: "uploads", href: "/uploads", label: "Uploads", icon: UploadCloud },
  { id: "analytics", href: "/analytics", label: "Analytics", icon: BarChart3 },
];

function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

function numberFmt(value) {
  return new Intl.NumberFormat("en", { notation: value > 9999 ? "compact" : "standard" }).format(value || 0);
}

function useDashboardData(page) {
  const [overview, setOverview] = useState(initialPayload.overview || null);
  const [clips, setClips] = useState(initialPayload.clips || null);
  const [analytics, setAnalytics] = useState(initialPayload.analytics || null);
  const [channels, setChannels] = useState(initialPayload.channels || null);
  const [aiInsights, setAiInsights] = useState(initialPayload.aiInsights || null);
  const [uploadIntelligence, setUploadIntelligence] = useState(initialPayload.uploadIntelligence || null);
  const [revenue, setRevenue] = useState(initialPayload.revenue || null);
  const [trends, setTrends] = useState(initialPayload.trends || null);
  const [learning, setLearning] = useState(initialPayload.learning || null);
  const [uploads, setUploads] = useState(initialPayload.uploads || null);
  const [logs, setLogs] = useState(initialPayload.logs || null);
  const [settings, setSettings] = useState(initialPayload.settings || null);
  const [loading, setLoading] = useState(false);

  async function load(target = page) {
    setLoading(true);
    try {
      const requests = [fetch("/dashboard/api/overview").then((r) => r.json())];
      if (["review", "generate"].includes(target)) {
        requests.push(fetch("/dashboard/api/clips?limit=36&sort=score").then((r) => r.json()));
      } else {
        requests.push(Promise.resolve(clips));
      }
      if (target === "analytics") {
        requests.push(fetch("/dashboard/api/analytics").then((r) => r.json()));
      } else {
        requests.push(Promise.resolve(analytics));
      }
      if (target === "sources") {
        requests.push(fetch("/dashboard/api/channels").then((r) => r.json()));
      } else {
        requests.push(Promise.resolve(channels));
      }
      requests.push(Promise.resolve(aiInsights));
      if (["uploads", "analytics"].includes(target)) {
        requests.push(fetch("/dashboard/api/upload-intelligence").then((r) => r.json()));
      } else {
        requests.push(Promise.resolve(uploadIntelligence));
      }
      requests.push(Promise.resolve(revenue));
      requests.push(Promise.resolve(trends));
      requests.push(Promise.resolve(learning));
      if (["review", "uploads"].includes(target)) {
        requests.push(fetch("/dashboard/api/uploads").then((r) => r.json()));
      } else {
        requests.push(Promise.resolve(uploads));
      }
      requests.push(Promise.resolve(logs));
      requests.push(Promise.resolve(settings));

      const [
        nextOverview,
        nextClips,
        nextAnalytics,
        nextChannels,
        nextAiInsights,
        nextUploadIntelligence,
        nextRevenue,
        nextTrends,
        nextLearning,
        nextUploads,
        nextLogs,
        nextSettings,
      ] = await Promise.all(requests);
      setOverview(nextOverview);
      if (nextClips) setClips(nextClips);
      if (nextAnalytics) setAnalytics(nextAnalytics);
      if (nextChannels) setChannels(nextChannels);
      if (nextAiInsights) setAiInsights(nextAiInsights);
      if (nextUploadIntelligence) setUploadIntelligence(nextUploadIntelligence);
      if (nextRevenue) setRevenue(nextRevenue);
      if (nextTrends) setTrends(nextTrends);
      if (nextLearning) setLearning(nextLearning);
      if (nextUploads) setUploads(nextUploads);
      if (nextLogs) setLogs(nextLogs);
      if (nextSettings) setSettings(nextSettings);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(page);
  }, [page]);

  useEffect(() => {
    if (page !== "generate") return undefined;
    const timer = window.setInterval(() => {
      fetch("/dashboard/api/logs")
        .then((r) => r.json())
        .then(setLogs)
        .catch(() => {});
    }, 5000);
    return () => window.clearInterval(timer);
  }, [page]);

  return {
    overview,
    clips,
    analytics,
    channels,
    aiInsights,
    uploadIntelligence,
    revenue,
    trends,
    learning,
    uploads,
    logs,
    settings,
    loading,
    reload: load,
  };
}

function App() {
  const [page, setPage] = useState(pageFromServer);
  const [modalClip, setModalClip] = useState(null);
  const data = useDashboardData(page);

  useEffect(() => {
    const onPop = () => setPage(pageIdFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function go(next, href) {
    setPage(next);
    window.history.pushState({}, "", href);
  }

  const stats = data.overview?.stats || {};
  return (
    <div className="min-h-screen overflow-x-hidden text-slate-100">
      <div className="pointer-events-none fixed inset-0 scanline opacity-[0.16]" />
      <div className="mx-auto flex w-full max-w-[1600px] gap-4 px-3 py-4 sm:px-4 lg:gap-5 lg:px-6">
        <Sidebar page={page} go={go} />
        <main className="w-full min-w-0 flex-1">
          <Topbar page={page} loading={data.loading} reload={() => data.reload(page)} stats={stats} />
          <MobileNav page={page} go={go} />
          <div className="mt-5">
            {page === "sources" && <SourcesPage data={data} />}
            {page === "generate" && <GeneratePage data={data} onPreview={setModalClip} />}
            {page === "review" && <ReviewQueuePage data={data} onPreview={setModalClip} />}
            {page === "uploads" && <UploadsPage data={data} />}
            {page === "analytics" && <AnalyticsPage data={data} />}
          </div>
        </main>
      </div>
      {modalClip && <ClipModal clip={modalClip} close={() => setModalClip(null)} />}
    </div>
  );
}

function pageIdFromPath(pathname) {
  if (pathname.includes("sources") || pathname.includes("channels")) return "sources";
  if (pathname.includes("generate") || pathname.includes("pipeline")) return "generate";
  if (pathname.includes("review") || pathname.includes("clips")) return "review";
  if (pathname.includes("uploads")) return "uploads";
  if (pathname.includes("analytics")) return "analytics";
  return "review";
}

function MobileNav({ page, go }) {
  return (
    <nav className="mt-3 flex gap-2 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.045] p-2 lg:hidden">
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => go(item.id, item.href)}
            className={cx("nav-link shrink-0 px-3", page === item.id && "active")}
          >
            <Icon size={17} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function Sidebar({ page, go }) {
  return (
    <aside className="sticky top-4 hidden h-[calc(100vh-2rem)] w-72 shrink-0 rounded-3xl glass-panel p-4 lg:block">
      <div className="flex items-center gap-3 px-2 py-2">
        <div className="grid h-11 w-11 place-items-center rounded-2xl bg-cyan-300 text-slate-950 shadow-lg shadow-cyan-400/20">
          <Sparkles size={22} />
        </div>
        <div>
          <p className="text-sm font-black tracking-tight text-white">AI Shorts Studio</p>
          <p className="text-xs text-slate-400">Private creator workflow</p>
        </div>
      </div>
      <nav className="scrollbar-thin mt-8 grid max-h-[55vh] gap-1.5 overflow-auto pr-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => go(item.id, item.href)}
              className={cx("nav-link text-left", page === item.id && "active")}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="absolute bottom-4 left-4 right-4 rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-4">
        <div className="mb-2 flex items-center gap-2 text-cyan-100">
          <Bot size={18} />
          <span className="text-sm font-bold">Today&apos;s Focus</span>
        </div>
        <p className="text-xs leading-5 text-slate-300">
          Review fast, keep the strongest hooks, and upload only rights-safe Shorts.
        </p>
      </div>
    </aside>
  );
}

function Topbar({ page, loading, reload, stats }) {
  return (
    <header className="glass-panel overflow-hidden rounded-3xl px-4 py-4 sm:px-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.24em] text-cyan-200">
            <Radio size={14} className="animate-pulse" /> Personal AI Shorts Studio
          </p>
          <h1 className="mt-2 max-w-full break-words text-2xl font-black leading-tight tracking-tight text-white sm:text-3xl md:text-4xl">
            {titleForPage(page)}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="hidden rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-300 md:block">
            {numberFmt(stats.active_pipelines)} running jobs
          </div>
          <button className="control-button w-full sm:w-auto" onClick={reload} type="button">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />} Sync
          </button>
          <button className="primary-button w-full sm:w-auto" type="button" onClick={() => fetch("/api/process", { method: "POST" })}>
            <Zap size={16} /> Generate Shorts
          </button>
        </div>
      </div>
    </header>
  );
}

function titleForPage(page) {
  return {
    sources: "Sources",
    generate: "Generate Shorts",
    review: "Review Queue",
    uploads: "Private Uploads",
    analytics: "Creator Analytics",
  }[page];
}

function Overview({ data, onPreview }) {
  const overview = data.overview;
  if (!overview) return <SkeletonGrid />;
  const stats = overview.stats;
  return (
    <div className="grid gap-5">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <StatCard title="Processed videos" value={stats.processed_videos} icon={Video} tone="cyan" />
        <StatCard title="Generated shorts" value={stats.generated_shorts} icon={Clapperboard} tone="violet" />
        <StatCard title="Queued uploads" value={stats.queued_uploads} icon={UploadCloud} tone="amber" />
        <StatCard title="Avg retention" value={`${stats.average_retention || 0}%`} icon={Gauge} tone="emerald" />
        <StatCard title="Total views" value={numberFmt(stats.total_views)} icon={Eye} tone="rose" />
        <StatCard title="Active pipelines" value={stats.active_pipelines} icon={Activity} tone="cyan" />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.4fr_0.9fr]">
        <ChartPanel title="Views and retention" subtitle="Performance trend by capture date">
          <PerformanceChart data={overview.timeline} />
        </ChartPanel>
        <AIInsights insights={overview.insights} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <ShortsStrip clips={data.clips?.items || overview.clips} onPreview={onPreview} />
        <ActivityFeed items={overview.activity} />
      </section>
    </div>
  );
}

function StatCard({ title, value, icon: Icon, tone }) {
  const color = {
    cyan: "from-cyan-300/20 text-cyan-200",
    violet: "from-violet-400/20 text-violet-200",
    amber: "from-amber-300/20 text-amber-200",
    emerald: "from-emerald-300/20 text-emerald-200",
    rose: "from-rose-300/20 text-rose-200",
  }[tone];
  return (
    <article className="soft-card group overflow-hidden p-4">
      <div className={cx("mb-5 flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br to-white/[0.04]", color)}>
        <Icon size={20} />
      </div>
      <p className="text-3xl font-black tracking-tight text-white">{value}</p>
      <p className="mt-1 text-sm text-slate-400">{title}</p>
      <div className="mt-4 h-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-cyan-300 to-violet-300 transition-all duration-700 group-hover:w-full" />
      </div>
    </article>
  );
}

function ChartPanel({ title, subtitle, children }) {
  return (
    <section className="soft-card p-5">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-white">{title}</h2>
          <p className="text-sm text-slate-400">{subtitle}</p>
        </div>
        <Flame size={20} className="text-cyan-200" />
      </div>
      {children}
    </section>
  );
}

function PerformanceChart({ data }) {
  const canvas = useRef(null);
  useEffect(() => {
    if (!data?.length || !canvas.current) return undefined;
    const chart = new Chart(canvas.current, {
      type: "line",
      data: {
        labels: data.map((item) => item.label),
        datasets: [
          {
            label: "Views",
            data: data.map((item) => item.views),
            borderColor: "#22d3ee",
            backgroundColor: "rgba(34, 211, 238, 0.14)",
            fill: true,
            tension: 0.42,
            pointRadius: 3,
          },
          {
            label: "Retention",
            data: data.map((item) => item.retention),
            borderColor: "#a78bfa",
            backgroundColor: "rgba(167, 139, 250, 0.08)",
            fill: true,
            tension: 0.42,
            pointRadius: 3,
          },
        ],
      },
      options: chartOptions(),
    });
    return () => chart.destroy();
  }, [data]);
  if (!data?.length) {
    return <EmptyState icon={BarChart3} title="No real analytics collected yet." text="Upload a reviewed clip and let the scheduled YouTube snapshots run." />;
  }
  return <canvas ref={canvas} className="h-[320px] w-full" />;
}

function chartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#cbd5e1", usePointStyle: true } },
      tooltip: { backgroundColor: "#0f172a", borderColor: "rgba(255,255,255,.1)", borderWidth: 1 },
    },
    scales: {
      x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,.08)" } },
      y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,.08)" } },
    },
  };
}

function AIInsights({ insights }) {
  return (
    <section className="soft-card p-5">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-white">AI Insights</h2>
          <p className="text-sm text-slate-400">Clip selection signals</p>
        </div>
        <Wand2 className="text-violet-200" size={20} />
      </div>
      <div className="grid gap-4">
        {(insights || []).map((item) => (
          <div key={item.label}>
            <div className="mb-2 flex justify-between text-sm">
              <span className="font-semibold text-slate-200">{item.label}</span>
              <span className="text-slate-400">{item.value}%</span>
            </div>
            <div className="h-2 rounded-full bg-white/10">
              <div className="h-full rounded-full bg-gradient-to-r from-cyan-300 via-violet-300 to-fuchsia-300" style={{ width: `${item.value}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ShortsStrip({ clips, onPreview }) {
  return (
    <section className="soft-card p-5">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-white">Top generated Shorts</h2>
          <p className="text-sm text-slate-400">Ranked by retention probability</p>
        </div>
        <Rocket size={20} className="text-cyan-200" />
      </div>
      {clips?.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {clips.slice(0, 6).map((clip) => (
            <ClipCard key={clip.id} clip={clip} onPreview={onPreview} compact />
          ))}
        </div>
      ) : (
        <EmptyState icon={Film} title="No Shorts generated yet" text="Run the pipeline to create your first clip." />
      )}
    </section>
  );
}

function ActivityFeed({ items }) {
  return (
    <section className="soft-card p-5">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-white">Recent activity</h2>
          <p className="text-sm text-slate-400">System events and queue movement</p>
        </div>
        <Activity size={20} className="text-violet-200" />
      </div>
      <div className="grid gap-3">
        {items?.length ? (
          items.map((item, index) => (
            <div key={`${item.type}-${index}`} className="rounded-2xl border border-white/10 bg-black/20 p-3">
              <div className="flex items-start gap-3">
                <span className="mt-1 h-2.5 w-2.5 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,.8)]" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-100">{item.message}</p>
                  <p className="text-xs text-slate-500">{item.status} - {formatTime(item.time)}</p>
                </div>
              </div>
            </div>
          ))
        ) : (
          <EmptyState icon={CalendarClock} title="Quiet workspace" text="Events will appear here as the agent runs." />
        )}
      </div>
    </section>
  );
}

function PipelinePage({ data }) {
  const stages = data.overview?.pipeline || [];
  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_0.9fr]">
      <section className="soft-card p-5">
        <h2 className="text-xl font-black text-white">Pipeline flow</h2>
        <p className="mt-1 text-sm text-slate-400">Download to upload queue with live status markers.</p>
        <div className="mt-6 grid gap-4">
          {stages.map((stage, index) => (
            <PipelineStage key={stage.name} stage={stage} index={index} />
          ))}
        </div>
      </section>
      <LogsPage logs={data.logs} compact />
    </div>
  );
}

function PipelineStage({ stage, index }) {
  const icons = [Download, Bot, Sparkles, Wand2, Film, UploadCloud];
  const Icon = icons[index] || CheckCircle2;
  return (
    <div className="relative rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      <div className="flex items-center gap-4">
        <div className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-300/10 text-cyan-200 ring-1 ring-cyan-300/20">
          <Icon size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-black text-white">{stage.name}</h3>
            <span className={cx("rounded-full px-2 py-1 text-xs font-bold", stage.status === "active" ? "bg-cyan-300/15 text-cyan-200" : "bg-white/10 text-slate-300")}>
              {stage.status}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-400">{stage.count} items - timing {stage.timing}</p>
        </div>
        <ChevronRight className="text-slate-600" />
      </div>
    </div>
  );
}

function ReviewQueuePage({ data, onPreview }) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const clips = data.clips?.items || [];
  const visible = clips.filter((clip) => {
    const matchesFilter = filter === "all" || clip.status === filter || clip.upload_readiness?.status === filter;
    const haystack = `${clip.hook_text || ""} ${clip.title || ""} ${clip.source_title || ""}`.toLowerCase();
    return matchesFilter && haystack.includes(query.trim().toLowerCase());
  });
  return (
    <div className="grid gap-5">
      <section className="soft-card p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="relative max-w-md flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="w-full rounded-2xl border border-white/10 bg-black/20 py-3 pl-10 pr-4 text-sm text-white outline-none ring-cyan-300/30 transition focus:ring-4"
              placeholder="Search hooks, titles, sources"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {["all", "detected", "approved", "ready", "needs_work"].map((item) => (
              <button key={item} className={cx("control-button capitalize", filter === item && "border-cyan-300/40 bg-cyan-300/10 text-cyan-100")} onClick={() => setFilter(item)} type="button">
                {item.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
      </section>
      {visible.length ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {visible.map((clip) => <ClipCard key={clip.id} clip={clip} onPreview={onPreview} />)}
        </section>
      ) : (
        <EmptyState icon={Clapperboard} title="No Shorts match this view" text="Try another filter or generate a new batch." />
      )}
    </div>
  );
}

function ClipCard({ clip, onPreview, compact = false }) {
  const canReview = Number.isFinite(Number(clip.id));
  const readiness = clip.upload_readiness || { label: "Needs review", status: "review" };
  const rights = clip.rights_status || { label: "Needs rights check", status: "needs_review" };
  return (
    <article className="group soft-card overflow-hidden">
      <div className={cx("relative bg-gradient-to-br from-slate-900 to-slate-950", compact ? "h-52" : "h-64 md:h-48 xl:h-40")}>
        {clip.clip_url ? (
          <video src={clip.clip_url} className="h-full w-full object-contain opacity-80 transition duration-300 group-hover:scale-[1.03] group-hover:opacity-100" muted playsInline preload="metadata" />
        ) : (
          <div className="grid h-full place-items-center text-slate-500"><Film size={38} /></div>
        )}
        <div className="absolute inset-x-3 top-3 flex items-center justify-between">
          <span className="rounded-full bg-black/60 px-3 py-1 text-xs font-black text-cyan-100 backdrop-blur">{clip.retention_score}%</span>
          <span className="rounded-full bg-black/60 px-3 py-1 text-xs font-bold text-slate-200 backdrop-blur">{clip.duration}s</span>
        </div>
        <button type="button" onClick={() => onPreview(clip)} className="absolute inset-0 grid place-items-center bg-black/0 opacity-0 transition duration-300 group-hover:bg-black/35 group-hover:opacity-100">
          <span className="grid h-14 w-14 place-items-center rounded-full bg-cyan-300 text-slate-950"><Play fill="currentColor" /></span>
        </button>
      </div>
      <div className="p-4">
        <div className="flex flex-wrap gap-2">
          <span className={cx("rounded-full px-3 py-1 text-xs font-black", readinessTone(readiness.status))}>{readiness.label}</span>
          <span className={cx("rounded-full px-3 py-1 text-xs font-black", rights.status === "cleared" ? "bg-emerald-300/15 text-emerald-200" : "bg-amber-300/15 text-amber-100")}>{rights.label}</span>
        </div>
        <h3 className="mt-3 line-clamp-1 text-lg font-black text-white">{clip.hook_text}</h3>
        <p className="mt-1 line-clamp-2 text-sm font-semibold text-slate-200">{clip.title}</p>
        <p className="mt-2 line-clamp-1 text-xs text-slate-500">{clip.source_title || `Source video #${clip.video_id}`}</p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-black/20 px-3 py-1 font-black text-white">{clip.duration}s <span className="font-medium text-slate-500">duration</span></span>
          <span className="rounded-full bg-black/20 px-3 py-1 font-black text-white">{clip.retention_score}% <span className="font-medium text-slate-500">retention</span></span>
          <span className="rounded-full bg-black/20 px-3 py-1 font-black capitalize text-white">{clip.hook_type || "hook"}</span>
        </div>
        <div className="scrollbar-thin mt-3 flex gap-2 overflow-x-auto pb-1">
          <button className="control-button shrink-0 px-3 py-2" onClick={() => onPreview(clip)} type="button"><Play size={15} /> Preview</button>
          <button className="control-button shrink-0 px-3 py-2" disabled={!canReview} onClick={() => reviewClip(clip.id, "approve")} type="button"><CheckCircle2 size={15} /> Approve</button>
          <button className="control-button shrink-0 px-3 py-2" disabled={!canReview} onClick={() => reviewClip(clip.id, "reject")} type="button"><Eye size={15} /> Reject</button>
          <button className="control-button shrink-0 px-3 py-2" disabled={!canReview} onClick={() => regenerateHook(clip.id)} type="button"><Wand2 size={15} /> Regenerate Hook</button>
          <button className="control-button shrink-0 px-3 py-2" disabled={!canReview} onClick={() => regenerateCaptions(clip.id)} type="button"><Bot size={15} /> Regenerate Captions</button>
          <button className="control-button shrink-0 px-3 py-2" disabled={!canReview} onClick={() => reviewClip(clip.id, "rerender")} type="button"><RefreshCw size={15} /> Re-render</button>
          <button className="primary-button shrink-0 px-3 py-2" disabled={!canReview} onClick={() => uploadPrivate(clip.id)} type="button"><UploadCloud size={15} /> Upload Private</button>
          {clip.clip_url && <a className="control-button shrink-0 px-3 py-2" href={clip.clip_url} download><Download size={15} /> Download</a>}
        </div>
      </div>
    </article>
  );
}

function readinessTone(status) {
  return {
    ready: "bg-emerald-300/15 text-emerald-200",
    queued: "bg-cyan-300/15 text-cyan-100",
    uploaded: "bg-cyan-300/15 text-cyan-100",
    needs_work: "bg-amber-300/15 text-amber-100",
    needs_rights: "bg-amber-300/15 text-amber-100",
    blocked: "bg-rose-300/15 text-rose-200",
    review: "bg-white/10 text-slate-200",
  }[status] || "bg-white/10 text-slate-200";
}

function reviewClip(clipId, action) {
  fetch(`/api/clips/${clipId}/review/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: "dashboard review" }),
  }).then(() => window.location.reload()).catch(() => {});
}

function regenerateCaptions(clipId) {
  fetch(`/api/clips/${clipId}/subtitles/regenerate`, {
    method: "POST",
  }).then(() => window.location.reload()).catch(() => {});
}

function regenerateHook(clipId) {
  fetch(`/api/clips/${clipId}/hooks/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preferred_type: null }),
  }).then(() => window.location.reload()).catch(() => {});
}

async function uploadPrivate(clipId) {
  const confirmation = window.prompt("Rights check: type OWNED, LICENSED, or TRANSFORMED to queue a private/unlisted upload.");
  if (!confirmation) return;
  const value = confirmation.trim().toUpperCase();
  if (!["OWNED", "LICENSED", "TRANSFORMED"].includes(value)) {
    window.alert("Upload cancelled. Confirm OWNED, LICENSED, or TRANSFORMED before queueing.");
    return;
  }
  const rights_review = {
    owned_content: value === "OWNED",
    licensed_content: value === "LICENSED",
    commentary_added: value === "TRANSFORMED",
    narration_added: value === "TRANSFORMED",
    transformative_edit: value === "TRANSFORMED",
    approved_for_upload: true,
    policy_notes: `Confirmed ${value.toLowerCase()} from review queue. Upload must remain private/unlisted until manually published.`,
  };
  const response = await fetch(`/api/clips/${clipId}/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scheduled_for: null, rights_review }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    window.alert(detail?.detail?.reasons?.join("\n") || detail?.detail?.message || "Upload gate failed.");
    return;
  }
  window.location.reload();
}

function SourcesPage({ data }) {
  const sources = data.channels?.sources || [];
  const channels = data.channels?.items || [];
  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
      <section className="soft-card p-5">
        <h2 className="text-xl font-black text-white">Add source</h2>
        <form className="mt-5 grid gap-3" onSubmit={addSource}>
          <select name="source_type" className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none ring-cyan-300/30 focus:ring-4">
            <option value="url">YouTube link</option>
            <option value="playlist">Playlist</option>
            <option value="channel">Channel</option>
            <option value="topic">Topic / search term</option>
          </select>
          <input name="url" required className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none ring-cyan-300/30 focus:ring-4" placeholder="Paste a video, playlist, channel, or topic" />
          <input name="label" className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none ring-cyan-300/30 focus:ring-4" placeholder="Optional label" />
          <button className="primary-button" type="submit"><Globe2 size={16} /> Add Source</button>
        </form>
      </section>
      <section className="soft-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-black text-white">Saved sources</h2>
          <button className="control-button" type="button" onClick={() => fetch("/api/sources/scan", { method: "POST" }).then(() => window.location.reload())}>
            <Search size={16} /> Scan Sources
          </button>
        </div>
        <div className="mt-5 grid gap-3">
          {sources.length ? sources.map((source) => (
            <div key={source.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-black text-white">{source.label || source.url}</p>
                  <p className="mt-1 truncate text-sm text-slate-500">{source.url}</p>
                </div>
                <span className="rounded-full bg-cyan-300/15 px-3 py-1 text-xs font-black uppercase text-cyan-100">{source.source_type}</span>
              </div>
            </div>
          )) : channels.length ? channels.map((channel) => (
            <div key={channel.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="font-black text-white">{channel.name}</p>
              <p className="mt-1 truncate text-sm text-slate-500">{channel.url}</p>
            </div>
          )) : <EmptyState icon={Globe2} title="No sources yet" text="Add one link, playlist, channel, or topic to start generating." />}
        </div>
      </section>
    </div>
  );
}

function addSource(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  fetch("/api/sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_type: form.get("source_type"),
      url: form.get("url"),
      label: form.get("label") || null,
    }),
  }).then(() => window.location.reload()).catch(() => {});
}

function GeneratePage({ data, onPreview }) {
  const recentVideos = data.overview?.videos || [];
  const recentClips = data.clips?.items || [];
  return (
    <div className="grid gap-5">
      <section className="grid gap-4 md:grid-cols-3">
        <button className="primary-button min-h-24 justify-start px-5 text-left" type="button" onClick={() => fetch("/api/sources/scan", { method: "POST" }).then(() => window.location.reload())}>
          <Search size={20} /> Scan sources
        </button>
        <button className="primary-button min-h-24 justify-start px-5 text-left" type="button" onClick={() => fetch("/api/process", { method: "POST" }).then(() => window.location.reload())}>
          <Zap size={20} /> Generate candidate Shorts
        </button>
        <button className="control-button min-h-24 justify-start px-5 text-left" type="button" onClick={() => fetch("/api/jobs/run-next", { method: "POST" }).then(() => window.location.reload())}>
          <Play size={20} /> Run next local job
        </button>
      </section>
      <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <RankedList title="Recent source videos" items={recentVideos.map((video) => ({ label: video.title, value: video.status }))} />
        <section className="soft-card p-5">
          <h2 className="text-lg font-black text-white">Latest candidates</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {recentClips.slice(0, 4).map((clip) => <ClipCard key={clip.id} clip={clip} onPreview={onPreview} compact />)}
            {!recentClips.length && <EmptyState icon={Clapperboard} title="No candidates yet" text="Run generation after adding a source." />}
          </div>
        </section>
      </section>
    </div>
  );
}

function UploadsPage({ data }) {
  const uploads = data.uploads?.items || [];
  const suggestedTimes = data.uploadIntelligence?.suggested_times || [];
  return (
    <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
      <section className="soft-card p-5">
        <h2 className="text-xl font-black text-white">Private upload queue</h2>
        <div className="mt-5 grid gap-3">
          {uploads.length ? uploads.map((upload) => (
            <div key={upload.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-black text-white">{upload.hook_text || upload.clip_title || `Clip #${upload.clip_id}`}</p>
                  <p className="mt-1 text-sm text-slate-500">{upload.privacy_status} - {upload.status}</p>
                </div>
                <span className="rounded-full bg-cyan-300/15 px-3 py-1 text-xs font-black text-cyan-100">{upload.scheduled_for ? formatDateTime(upload.scheduled_for) : "private now"}</span>
              </div>
            </div>
          )) : <EmptyState icon={UploadCloud} title="No uploads queued" text="Approve a candidate, then use Upload Private from the review queue." />}
        </div>
      </section>
      <RankedList title="Useful upload windows" items={suggestedTimes.map((item) => ({ label: item.time, value: `${item.score}%` }))} />
    </div>
  );
}

function AnalyticsPage({ data }) {
  const analytics = data.analytics;
  if (!analytics) return <SkeletonGrid />;
  const message = analytics.truth_mode?.message;
  const timeline = analytics.timeline || [];
  const stats = data.overview?.stats || {};
  const avgWatch = timeline.length
    ? Math.round(timeline.reduce((sum, item) => sum + Number(item.average_view_duration_seconds || 0), 0) / timeline.length)
    : 0;
  return (
    <div className="grid gap-5">
      {message && <Notice text={message} />}
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard title="Views" value={numberFmt(stats.total_views)} icon={Eye} tone="cyan" />
        <StatCard title="Retention" value={`${stats.average_retention || 0}%`} icon={Gauge} tone="emerald" />
        <StatCard title="Avg watch" value={avgWatch ? `${avgWatch}s` : "No data"} icon={Activity} tone="amber" />
      </section>
      <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <ChartPanel title="Views and retention" subtitle="Real YouTube data when available">
          <PerformanceChart data={timeline} />
        </ChartPanel>
        <RankedList title="Best upload times" items={(data.uploadIntelligence?.suggested_times || []).map((item) => ({ label: item.time, value: `${item.score}%` }))} />
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <RankedList title="Best hooks" items={(analytics.best_hooks || []).map((item) => ({ label: item.hook, value: `${item.score}%` }))} />
        <RankedList title="Top Shorts" items={(analytics.top_clips || []).map((item) => ({ label: item.hook_text, value: `${item.retention_score}%` }))} />
      </section>
    </div>
  );
}

function AIInsightsPage({ data, onPreview }) {
  const insights = data.aiInsights;
  if (!insights) return <SkeletonGrid />;
  const summary = insights.summary || {};
  return (
    <div className="grid gap-5">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard title="Avg retention" value={`${summary.avg_retention || 0}%`} icon={Gauge} tone="cyan" />
        <StatCard title="Viral probability" value={`${summary.avg_viral_probability || 0}%`} icon={Flame} tone="violet" />
        <StatCard title="Auto-ready" value={summary.auto_schedule_ready || 0} icon={Rocket} tone="emerald" />
        <StatCard title="Review queue" value={summary.review_queue || 0} icon={Eye} tone="amber" />
      </section>
      <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <AIInsights insights={insights.signals} />
        <RankedList title="Why clips are selected" items={(insights.top_reasons || []).map((item) => ({ label: item.label, value: item.value }))} />
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <RankedList title="Hook variants winning" items={(data.learning?.hook_rankings || []).map((item) => ({ label: `${item.hook_type} (${item.count})`, value: `${item.score}%` }))} />
        <RankedList title="Dead-zone avoidance" items={(insights.clips || []).map((clip) => ({ label: clip.hook_text, value: `${clip.insights?.watchability || clip.retention_score}% watchable` }))} />
      </section>
      <section className="soft-card p-5">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-black text-white">Highest probability Shorts</h2>
            <p className="text-sm text-slate-400">Retention, hook strength, curiosity, and pacing combined.</p>
          </div>
          <Brain size={20} className="text-cyan-200" />
        </div>
        {insights.clips?.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {insights.clips.map((clip) => <ClipCard key={clip.id} clip={clip} onPreview={onPreview} compact />)}
          </div>
        ) : (
          <EmptyState icon={Brain} title="No clip intelligence yet" text="New renders will receive retention scores automatically." />
        )}
      </section>
    </div>
  );
}

function UploadIntelligencePage({ data }) {
  const payload = data.uploadIntelligence;
  if (!payload) return <SkeletonGrid />;
  return (
    <div className="grid gap-5">
      <section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="soft-card p-5">
          <h2 className="text-xl font-black text-white">Recommended uploads today</h2>
          <p className="mt-1 text-sm text-slate-400">Local confidence score based on retention, channel schedule, and packaging.</p>
          <div className="mt-5 grid gap-3">
            {(payload.recommended_today || []).length ? payload.recommended_today.map((item) => (
              <div key={item.id || `${item.clip_id}-${item.recommended_for}`} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-black text-white">{item.title || `Clip #${item.clip_id}`}</p>
                    <p className="mt-1 text-sm text-slate-400">{item.rationale}</p>
                  </div>
                  <span className="rounded-full bg-cyan-300/15 px-3 py-1 text-xs font-black text-cyan-100">{item.confidence_score}%</span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                  <span className="rounded-full bg-white/10 px-3 py-1">{formatDateTime(item.recommended_for)}</span>
                  {(item.hashtags || []).slice(0, 4).map((tag) => <span key={tag} className="rounded-full bg-white/10 px-3 py-1">{tag}</span>)}
                </div>
              </div>
            )) : <EmptyState icon={UploadCloud} title="No upload recommendations yet" text="Generated clips will appear here after scoring." />}
          </div>
        </section>
        <section className="soft-card p-5">
          <h2 className="text-xl font-black text-white">Best upload windows</h2>
          <p className="mt-1 text-sm text-slate-400">Schedule priors learned from local channel profiles.</p>
          <div className="mt-5 grid gap-3">
            {(payload.suggested_times || []).map((item, index) => (
              <div key={`${item.time}-${index}`} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                <div>
                  <p className="font-black text-white">{item.time}</p>
                  <p className="text-sm text-slate-400">{item.niche || item.channel || "Studio default"}</p>
                </div>
                <MetricRing value={item.score || 0} />
              </div>
            ))}
          </div>
        </section>
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <RankedList title="Schedule patterns" items={(payload.schedule_patterns || []).map((item) => ({ label: `${item.label} - ${item.time}`, value: `${item.score}%` }))} />
        <RankedList title="Auto-upload candidates" items={(payload.auto_upload_ready || []).map((item) => ({ label: item.title || `Clip #${item.clip_id}`, value: `${item.confidence_score}%` }))} />
      </section>
    </div>
  );
}

function RevenuePage({ data }) {
  const revenue = data.revenue;
  if (!revenue) return <SkeletonGrid />;
  const summary = revenue.summary || {};
  return (
    <div className="grid gap-5">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <StatCard title="Estimated revenue" value={`$${summary.estimated_revenue || 0}`} icon={DollarSign} tone="emerald" />
        <StatCard title="Projected monthly" value={`$${summary.projected_monthly || 0}`} icon={TrendingUp} tone="cyan" />
        <StatCard title="Views" value={numberFmt(summary.views)} icon={Eye} tone="violet" />
        <StatCard title="Watch hours" value={summary.watch_time_hours || 0} icon={Activity} tone="amber" />
        <StatCard title="Avg RPM" value={`$${summary.average_rpm || 0}`} icon={Gauge} tone="rose" />
      </section>
      <section className="grid gap-5 xl:grid-cols-[1fr_0.8fr]">
        <RankedList title="Top earning channels" items={(revenue.top_channels || []).map((item) => ({ label: item.name, value: `$${item.estimated_revenue}` }))} />
        <RankedList title="Forecast" items={(revenue.forecast || []).map((item) => ({ label: item.label, value: `$${item.value}` }))} />
      </section>
      <section className="soft-card p-5">
        <h2 className="text-lg font-black text-white">Top performing Shorts by revenue</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {(revenue.top_shorts || []).map((item, index) => (
            <div key={`${item.clip_id}-${index}`} className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Clip #{item.clip_id || index + 1}</p>
              <p className="mt-2 text-2xl font-black text-white">${item.estimated_revenue}</p>
              <p className="mt-1 text-sm text-slate-400">{numberFmt(item.views)} views - {item.watch_time_hours} watch hours</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function TrendCenterPage({ data }) {
  const trends = data.trends;
  if (!trends) return <SkeletonGrid />;
  return (
    <div className="grid gap-5">
      <section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="soft-card p-5">
          <h2 className="text-xl font-black text-white">Trending topics</h2>
          <p className="mt-1 text-sm text-slate-400">Local keywords mined from source metadata, clips, hooks, and outcomes.</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {(trends.top_topics || []).map((item) => (
              <span key={`${item.niche_type}-${item.keyword}`} className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-4 py-2 text-sm font-bold text-cyan-100">
                {item.keyword} <span className="text-slate-400">{item.score}</span>
              </span>
            ))}
          </div>
        </section>
        <RankedList title="Viral pattern analysis" items={(trends.trend_types || []).map((item) => ({ label: item.name, value: `${item.score}%` }))} />
      </section>
      <section className="grid gap-5 xl:grid-cols-3">
        <RankedList title="Rising topics" items={(trends.heat?.rising_topics || []).map((item) => ({ label: item.keyword, value: `+${item.velocity}` }))} />
        <RankedList title="Trending hooks" items={(trends.heat?.trending_hooks || []).map((item) => ({ label: `${item.label} (${item.count})`, value: `${item.heat}%` }))} />
        <RankedList title="Overused trends" items={(trends.heat?.overused_trends || []).map((item) => ({ label: item.keyword, value: item.score }))} />
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        {Object.entries(trends.by_niche || {}).slice(0, 4).map(([niche, items]) => (
          <section key={niche} className="soft-card p-5">
            <h3 className="text-lg font-black capitalize text-white">{niche}</h3>
            <div className="mt-4 grid gap-2">
              {items.slice(0, 6).map((item) => (
                <div key={item.keyword} className="flex items-center justify-between rounded-2xl border border-white/10 bg-black/20 p-3">
                  <span className="font-semibold text-slate-200">{item.keyword}</span>
                  <span className={cx("text-sm font-black", item.velocity >= 0 ? "text-emerald-300" : "text-rose-300")}>{item.velocity >= 0 ? "+" : ""}{item.velocity}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </section>
    </div>
  );
}

function LearningPage({ data }) {
  const learning = data.learning;
  if (!learning) return <SkeletonGrid />;
  const dataset = learning.dataset || {};
  return (
    <div className="grid gap-5">
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard title="Training examples" value={dataset.total_examples || 0} icon={Database} tone="cyan" />
        <StatCard title="Successful clips" value={dataset.successful_examples || 0} icon={Target} tone="emerald" />
        <StatCard title="Failed clips" value={dataset.failed_examples || 0} icon={Lightbulb} tone="amber" />
      </section>
      <section className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <section className="soft-card p-5">
          <h2 className="text-xl font-black text-white">What the AI has learned</h2>
          <div className="mt-5 grid gap-3">
            {(learning.learnings || []).map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-black text-white">{item.label}</p>
                  <span className="text-sm font-black text-cyan-200">{item.confidence}%</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-400">{item.insight}</p>
              </div>
            ))}
          </div>
        </section>
        <section className="grid gap-5">
          <RankedList title="Best patterns" items={(learning.best_patterns || []).map((item) => ({ label: `${item.pattern} (${item.count})`, value: `${item.score}%` }))} />
          <RankedList title="Avoid patterns" items={(learning.avoid_patterns || []).map((item) => ({ label: `${item.pattern} (${item.count})`, value: `${item.score}%` }))} />
        </section>
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <RankedList title="Hook performance" items={(learning.hook_rankings || []).map((item) => ({ label: `${item.hook_type} (${item.count})`, value: `${item.score}%` }))} />
        <section className="soft-card p-5">
          <h2 className="text-xl font-black text-white">Viral pattern memory</h2>
          <div className="mt-5 grid gap-3">
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Best duration</p>
              <p className="mt-2 text-2xl font-black text-white">{learning.viral_patterns?.best_duration ? `${learning.viral_patterns.best_duration}s` : "No real data"}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Dead-zone ceiling</p>
              <p className="mt-2 text-2xl font-black text-white">{learning.viral_patterns?.dead_zone_threshold ? `${learning.viral_patterns.dead_zone_threshold}%` : "No real data"}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(learning.viral_patterns?.best_upload_times || []).map((time) => <span key={time} className="rounded-full bg-cyan-300/10 px-3 py-1 text-sm font-bold text-cyan-100">{time}</span>)}
            </div>
          </div>
        </section>
      </section>
    </div>
  );
}

function EngagementChart({ data }) {
  const canvas = useRef(null);
  useEffect(() => {
    if (!data?.length || !canvas.current) return undefined;
    const chart = new Chart(canvas.current, {
      type: "bar",
      data: {
        labels: data.map((item) => item.label),
        datasets: [
          { label: "Likes", data: data.map((item) => item.likes), backgroundColor: "rgba(34, 211, 238, .42)", borderRadius: 8 },
          { label: "Comments", data: data.map((item) => item.comments), backgroundColor: "rgba(167, 139, 250, .46)", borderRadius: 8 },
        ],
      },
      options: chartOptions(),
    });
    return () => chart.destroy();
  }, [data]);
  if (!data?.length) {
    return <EmptyState icon={BarChart3} title="No real analytics collected yet." text="Likes, comments, and CTR appear only after YouTube returns real data." />;
  }
  return <canvas ref={canvas} className="h-[320px] w-full" />;
}

function RankedList({ title, items }) {
  return (
    <section className="soft-card p-5">
      <h2 className="text-lg font-black text-white">{title}</h2>
      <div className="mt-4 grid gap-3">
        {items.length ? items.map((item, index) => (
          <div key={`${item.label}-${index}`} className="flex items-center justify-between rounded-2xl border border-white/10 bg-black/20 p-3">
            <div className="flex items-center gap-3">
              <span className="grid h-8 w-8 place-items-center rounded-xl bg-white/10 text-xs font-black text-cyan-200">{index + 1}</span>
              <span className="text-sm font-semibold text-slate-200">{item.label}</span>
            </div>
            <span className="text-sm font-black text-white">{item.value}</span>
          </div>
        )) : <EmptyState icon={BarChart3} title="No ranking data" text="Analytics will fill in after uploads." />}
      </div>
    </section>
  );
}

function MetricRing({ value }) {
  const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="grid h-12 w-12 place-items-center rounded-full border border-cyan-300/25 bg-cyan-300/10 text-xs font-black text-cyan-100">
      {safeValue}%
    </div>
  );
}

function ChannelsPage({ data }) {
  const channels = data.channels?.items || [];
  const network = data.channels?.network || {};
  return (
    <div className="grid gap-5">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard title="Managed channels" value={network.managed_channels || channels.length} icon={Globe2} tone="cyan" />
        <StatCard title="Active channels" value={network.active_channels || 0} icon={Activity} tone="emerald" />
        <StatCard title="Generated clips" value={network.total_clips || 0} icon={Clapperboard} tone="violet" />
        <StatCard title="Avg posts/day" value={network.avg_upload_frequency || 0} icon={CalendarClock} tone="amber" />
      </section>
      <section className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
      <section className="soft-card p-5">
        <h2 className="text-xl font-black text-white">Add channel</h2>
        <p className="mt-1 text-sm text-slate-400">Monitor a YouTube channel and attach a niche strategy profile.</p>
        <form className="mt-5 grid gap-3" onSubmit={submitChannel}>
          <input name="url" required className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none ring-cyan-300/30 focus:ring-4" placeholder="YouTube channel URL or UC id" />
          <input name="name" className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none ring-cyan-300/30 focus:ring-4" placeholder="Creator label" />
          <select name="niche_type" className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none ring-cyan-300/30 focus:ring-4">
            <option value="general">General clips</option>
            <option value="gaming">Gaming</option>
            <option value="nature/survival">Nature / Survival</option>
            <option value="podcast">Podcast clips</option>
            <option value="documentary">Documentary</option>
          </select>
          <input name="hook_style" className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none ring-cyan-300/30 focus:ring-4" placeholder="Hook style, e.g. curiosity gap" />
          <button className="primary-button" type="submit"><Globe2 size={16} /> Add channel</button>
        </form>
      </section>
      <section className="soft-card p-5">
        <h2 className="text-xl font-black text-white">Monitored channels</h2>
        <div className="mt-5 grid gap-3">
          {channels.length ? channels.map((channel) => (
            <div key={channel.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-bold text-white">{channel.name}</p>
                <p className="truncate text-sm text-slate-500">{channel.url}</p>
              </div>
              <span className={cx("rounded-full px-3 py-1 text-xs font-black", channel.active ? "bg-emerald-300/15 text-emerald-200" : "bg-white/10 text-slate-400")}>{channel.active ? "Active" : "Paused"}</span>
              </div>
              <div className="mt-4 grid gap-2 text-xs text-slate-400 sm:grid-cols-4">
                <span className="rounded-full bg-white/10 px-3 py-1 capitalize">{channel.niche_type || "general"}</span>
                <span className="rounded-full bg-white/10 px-3 py-1">{channel.hook_style || "curiosity gap"}</span>
                <span className="rounded-full bg-white/10 px-3 py-1">{channel.upload_frequency || 2}/day</span>
                <span className="rounded-full bg-white/10 px-3 py-1">{numberFmt(channel.views)} views</span>
              </div>
            </div>
          )) : <EmptyState icon={Globe2} title="No channels yet" text="Add a creator channel to start monitoring uploads." />}
        </div>
      </section>
      </section>
    </div>
  );
}

function submitChannel(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  fetch("/api/channels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: form.get("url"),
      name: form.get("name") || null,
      niche_type: form.get("niche_type") || "general",
      hook_style: form.get("hook_style") || "curiosity gap",
    }),
  }).then(() => window.location.reload());
}

function LogsPage({ logs, compact = false }) {
  const items = logs?.items || [];
  return (
    <section className={cx("soft-card overflow-hidden", !compact && "min-h-[70vh]")}>
      <div className="border-b border-white/10 p-5">
        <h2 className="flex items-center gap-2 text-xl font-black text-white"><Terminal size={20} /> Live logs</h2>
        <p className="mt-1 text-sm text-slate-400">Downloader, FFmpeg, AI scoring, rendering, and queue activity.</p>
      </div>
      <div className="scrollbar-thin max-h-[640px] overflow-auto bg-black/30 p-4 font-mono text-sm">
        {items.length ? items.map((item, index) => (
          <div key={index} className="mb-2 grid grid-cols-[92px_72px_1fr] gap-3 rounded-xl px-3 py-2 text-slate-300 hover:bg-white/[0.04]">
            <span className="text-slate-500">{formatTime(item.timestamp)}</span>
            <span className={item.level === "error" ? "text-rose-300" : "text-cyan-300"}>{item.level}</span>
            <span><span className="text-violet-300">[{item.source}]</span> {item.message}</span>
          </div>
        )) : <EmptyState icon={Terminal} title="No logs yet" text="Pipeline events will stream here." />}
      </div>
    </section>
  );
}

function SettingsPage({ settings }) {
  const values = settings || {};
  const rows = [
    ["Ollama model", values.ollama_model],
    ["Ollama endpoint", values.ollama_base_url],
    ["FFmpeg quality", values.ffmpeg_quality ? `CRF ${values.ffmpeg_quality.crf}, ${values.ffmpeg_quality.preset}` : ""],
    ["Subtitle style", values.subtitle_style],
    ["Upload frequency", values.upload_frequency],
    ["Render quality", values.render_quality],
    ["Hook intensity", `${values.hook_intensity || 0}%`],
  ];
  return (
    <section className="soft-card p-5">
      <h2 className="text-xl font-black text-white">Creative controls</h2>
      <p className="mt-1 text-sm text-slate-400">Current render, AI, and publishing settings. Advanced write controls can be wired later without changing the dashboard shell.</p>
      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-white/10 bg-black/20 p-4">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{label}</p>
            <p className="mt-2 text-base font-bold text-white">{value || "Not configured"}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ClipModal({ clip, close }) {
  const variants = clip.hook_variants || [];
  const titleVariants = clip.title_variants || [];
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-xl" onClick={close}>
      <div className="glass-panel max-h-[92vh] w-full max-w-5xl overflow-auto rounded-3xl" onClick={(event) => event.stopPropagation()}>
        <div className="grid lg:grid-cols-[0.72fr_1fr]">
          <div className="bg-black">
            {clip.clip_url ? <video src={clip.clip_url} className="max-h-[78vh] w-full object-contain" controls autoPlay /> : <div className="grid aspect-[9/16] place-items-center"><Film /></div>}
          </div>
          <div className="p-6">
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-cyan-200">Retention score {clip.retention_score}%</p>
            <h2 className="mt-3 text-3xl font-black text-white">{clip.hook_text}</h2>
            <p className="mt-2 text-lg font-bold text-slate-200">{clip.title}</p>
            <p className="mt-1 text-sm text-slate-500">{clip.source_title || `Source video #${clip.video_id}`}</p>
            <p className="mt-3 leading-7 text-slate-300">{clip.reason || clip.description}</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button className="control-button px-3 py-2" onClick={() => regenerateHook(clip.id)} type="button"><Wand2 size={15} /> Regenerate Hook</button>
              <button className="control-button px-3 py-2" onClick={() => regenerateCaptions(clip.id)} type="button"><Bot size={15} /> Regenerate Captions</button>
              <button className="primary-button px-3 py-2" onClick={() => uploadPrivate(clip.id)} type="button"><UploadCloud size={15} /> Upload Private</button>
            </div>
            {!!variants.length && (
              <div className="mt-5">
                <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">Hook variants</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {variants.slice(0, 5).map((item) => <span key={item.text} className="rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-slate-200">{item.text}</span>)}
                </div>
              </div>
            )}
            {!!titleVariants.length && (
              <div className="mt-5">
                <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">Title variants</p>
                <div className="mt-2 grid gap-2">
                  {titleVariants.map((item) => <p key={item} className="rounded-xl bg-black/20 px-3 py-2 text-sm text-slate-200">{item}</p>)}
                </div>
              </div>
            )}
            <div className="mt-6 grid gap-3">
              {Object.entries(clip.insights || {}).map(([key, value]) => (
                <div key={key}>
                  <div className="mb-1 flex justify-between text-sm capitalize text-slate-300"><span>{key}</span><span>{value}%</span></div>
                  <div className="h-2 rounded-full bg-white/10"><div className="h-full rounded-full bg-cyan-300" style={{ width: `${value}%` }} /></div>
                </div>
              ))}
            </div>
            <button className="primary-button mt-8" onClick={close} type="button">Close preview</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="h-40 animate-pulse rounded-3xl border border-white/10 bg-white/[0.04]" />
      ))}
    </div>
  );
}

function EmptyState({ icon: Icon, title, text }) {
  return (
    <div className="grid min-h-56 place-items-center rounded-2xl border border-dashed border-white/10 bg-white/[0.03] p-8 text-center">
      <div>
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white/[0.06] text-cyan-200"><Icon /></div>
        <h3 className="mt-4 font-black text-white">{title}</h3>
        <p className="mt-1 max-w-sm text-sm text-slate-400">{text}</p>
      </div>
    </div>
  );
}

function Notice({ text }) {
  return (
    <div className="rounded-2xl border border-amber-300/20 bg-amber-300/10 px-4 py-3 text-sm font-semibold text-amber-100">
      {text}
    </div>
  );
}

function formatTime(value) {
  if (!value) return "now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "now";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(value) {
  if (!value) return "next open slot";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "next open slot";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

createRoot(document.getElementById("dashboard-root")).render(<App />);
