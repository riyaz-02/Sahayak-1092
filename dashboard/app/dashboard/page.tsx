"use client";

import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  BookOpen,
  CheckCircle2,
  Database,
  Edit3,
  FileText,
  History,
  Info,
  Mic,
  Network,
  PhoneCall,
  PhoneOutgoing,
  Radio,
  RefreshCw,
  Send,
  ShieldCheck,
  Users,
  X,
  Eye,
  Phone,
  MessageSquare,
  Clock,
  Tag,
  Zap,
  Globe
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type AnyRecord = Record<string, any>;

type DashboardData = {
  health: AnyRecord | null;
  activeCalls: AnyRecord[];
  callLogs: AnyRecord[];
  agents: AnyRecord[];
  queue: AnyRecord[];
  complaints: AnyRecord[];
  cases: AnyRecord[];
  events: AnyRecord[];
  agentTraces: AnyRecord[];
};

type CorrectionForm = {
  category: string;
  urgency: string;
  summary: string;
  resolution: string;
  notes: string;
};

type TabKey =
  | "overview"
  | "calls"
  | "queue"
  | "officers"
  | "complaints"
  | "knowledge"
  | "audit"
  | "test"
  | "call";

const API_BASE = "/api/sahayak";
const AUTO_REFRESH_MS = 15000;
const DASHBOARD_KEY_STORAGE = "sahayak.dashboard.key";

const emptyData: DashboardData = {
  health: null,
  activeCalls: [],
  callLogs: [],
  agents: [],
  queue: [],
  complaints: [],
  cases: [],
  events: [],
  agentTraces: []
};

const tabs: Array<{ key: TabKey; label: string; icon: typeof Activity }> = [
  { key: "overview", label: "Overview", icon: Activity },
  { key: "calls", label: "Live Calls", icon: PhoneCall },
  { key: "queue", label: "Queue", icon: Radio },
  { key: "officers", label: "Officers", icon: Users },
  { key: "complaints", label: "Complaints", icon: FileText },
  { key: "knowledge", label: "Knowledge", icon: BookOpen },
  { key: "audit", label: "Audit", icon: History },
  { key: "test", label: "Test Console", icon: Send },
  { key: "call", label: "Call Me", icon: PhoneOutgoing }
];

const categories = [
  "general",
  "theft",
  "accident",
  "domestic",
  "cyber",
  "noise",
  "missing_person",
  "suspicious_activity",
  "medical",
  "fire",
  "traffic",
  "harassment",
  "civic"
];

class DashboardAuthError extends Error {
  constructor(message = "Dashboard access key required") {
    super(message);
    this.name = "DashboardAuthError";
  }
}

function apiHeaders(dashboardKey = "") {
  const headers: Record<string, string> = {};
  if (dashboardKey) {
    headers["x-sahayak-dashboard-key"] = dashboardKey;
  }
  return headers;
}

function responseMessage(result: AnyRecord, fallback: string) {
  return (
    result.detail ||
    result.message ||
    result.error?.message ||
    result.error?.detail ||
    result.error ||
    fallback
  );
}

async function apiGet<T>(
  path: string,
  fallback: T,
  options: { signal?: AbortSignal; dashboardKey?: string } = {}
): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: apiHeaders(options.dashboardKey),
      signal: options.signal
    });
    if (response.status === 401 || response.status === 403) {
      throw new DashboardAuthError();
    }
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DashboardAuthError) {
      throw error;
    }
    return fallback;
  }
}

async function apiPost<T>(
  path: string,
  body: AnyRecord,
  fallback: T,
  dashboardKey = ""
): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...apiHeaders(dashboardKey)
      },
      body: JSON.stringify(body)
    });
    if (response.status === 401 || response.status === 403) {
      throw new DashboardAuthError();
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DashboardAuthError) {
      throw error;
    }
    return fallback;
  }
}

function compactSid(value?: string) {
  if (!value) {
    return "no-sid";
  }
  return value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-6)}` : value;
}

function percent(value: unknown) {
  const number = Number(value || 0);
  return `${Math.round(Math.max(0, Math.min(1, number)) * 100)}%`;
}

function statusTone(value?: string) {
  const status = (value || "").toLowerCase();
  if (status.includes("alert") || status.includes("distress") || status.includes("failed")) {
    return "red";
  }
  if (
    status.includes("resolved") ||
    status.includes("available") ||
    status.includes("ok") ||
    status.includes("healthy") ||
    status.includes("ready")
  ) {
    return "green";
  }
  if (status.includes("handover") || status.includes("queue") || status.includes("waiting")) {
    return "purple";
  }
  if (status.includes("match") || status.includes("vector")) {
    return "teal";
  }
  return "blue";
}

function Badge({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge ${tone || ""}`}>{children}</span>;
}

function MetricCard({
  label,
  value,
  detail,
  tone
}: {
  label: string;
  value: string | number;
  detail: string;
  tone?: string;
}) {
  return (
    <article className="metric-card">
      <div className="stat-label">{label}</div>
      <div className="metric-value" style={{ color: tone }}>
        {value}
      </div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData>(emptyData);
  const [tab, setTab] = useState<TabKey>("overview");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState("");
  const [authRequired, setAuthRequired] = useState(false);
  const [authInput, setAuthInput] = useState("");
  const [authError, setAuthError] = useState("");
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [selectedCallSid, setSelectedCallSid] = useState("");
  const [transcripts, setTranscripts] = useState<Record<string, AnyRecord[]>>({});
  const [handoverNotes, setHandoverNotes] = useState("");
  const [correction, setCorrection] = useState<CorrectionForm>({
    category: "general",
    urgency: "0.5",
    summary: "",
    resolution: "",
    notes: ""
  });
  const [testText, setTestText] = useState("My phone was stolen at Majestic bus stand");
  const [testLanguage, setTestLanguage] = useState("english");
  const [testCallSid, setTestCallSid] = useState(`demo-${Date.now()}`);
  const [testResult, setTestResult] = useState<AnyRecord | null>(null);
  // ── Call Me state ────────────────────────────────────
  const [callPhone, setCallPhone] = useState("");
  const [callIsd, setCallIsd] = useState("+91");
  const [callStatus, setCallStatus] = useState<"idle" | "calling" | "success" | "error">("idle");
  const [callResult, setCallResult] = useState<AnyRecord | null>(null);
  const [callError, setCallError] = useState("");
  // ── Complaint modal state ─────────────────────────────
  const [selectedComplaint, setSelectedComplaint] = useState<AnyRecord | null>(null);
  // ────────────────────────────────────────────────────
  const dataRef = useRef<DashboardData>(emptyData);
  const dashboardKeyRef = useRef("");
  const refreshControllerRef = useRef<AbortController | null>(null);
  const hydratedCorrectionSidRef = useRef("");

  useEffect(() => {
    const storedKey = window.localStorage.getItem(DASHBOARD_KEY_STORAGE) || "";
    dashboardKeyRef.current = storedKey;
    setAuthInput(storedKey);
  }, []);

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  const refresh = useCallback(async (mode: "initial" | "manual" | "background" = "manual") => {
    if (refreshControllerRef.current) {
      return;
    }

    const controller = new AbortController();
    refreshControllerRef.current = controller;
    const foregroundRefresh = mode !== "background";
    setRefreshing(true);
    if (foregroundRefresh) {
      setLoading(true);
    }

    try {
      const fallbackData = dataRef.current;
      const dashboardKey = dashboardKeyRef.current;
      const [
        health,
        active,
        logs,
        agents,
        queue,
        complaints,
        cases,
        events,
        agentTraces
      ] = await Promise.all([
        apiGet<AnyRecord | null>("/health", null, { dashboardKey, signal: controller.signal }),
        apiGet<AnyRecord>(
          "/api/active-calls",
          { active_calls: fallbackData.activeCalls },
          { dashboardKey, signal: controller.signal }
        ),
        apiGet<AnyRecord>(
          "/api/call-logs",
          { call_logs: fallbackData.callLogs },
          { dashboardKey, signal: controller.signal }
        ),
        apiGet<AnyRecord>(
          "/api/agents",
          { agents: fallbackData.agents },
          { dashboardKey, signal: controller.signal }
        ),
        apiGet<AnyRecord>(
          "/api/queue?include_inactive=true&limit=50",
          { queue: fallbackData.queue },
          { dashboardKey, signal: controller.signal }
        ),
        apiGet<AnyRecord>(
          "/api/complaints",
          { complaints: fallbackData.complaints },
          { dashboardKey, signal: controller.signal }
        ),
        apiGet<AnyRecord>(
          "/api/resolved-cases",
          { cases: fallbackData.cases },
          { dashboardKey, signal: controller.signal }
        ),
        apiGet<AnyRecord>(
          "/api/call-events?limit=80",
          { events: fallbackData.events },
          { dashboardKey, signal: controller.signal }
        ),
        apiGet<AnyRecord>(
          "/api/agent/traces?limit=20",
          { agent_traces: fallbackData.agentTraces },
          { dashboardKey, signal: controller.signal }
        )
      ]);

      if (!controller.signal.aborted) {
        setAuthRequired(false);
        setAuthError("");
        setData({
          health,
          activeCalls: active.active_calls || [],
          callLogs: logs.call_logs || [],
          agents: agents.agents || [],
          queue: queue.queue || [],
          complaints: complaints.complaints || [],
          cases: cases.cases || [],
          events: events.events || [],
          agentTraces: agentTraces.agent_traces || []
        });
        setLastUpdated(new Intl.DateTimeFormat("en-IN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit"
        }).format(new Date()));
      }
    } catch (refreshError) {
      if (refreshError instanceof DashboardAuthError && !controller.signal.aborted) {
        setAuthRequired(true);
        setAuthError("Enter the dashboard access key from dashboard/.env.local.");
      }
    } finally {
      if (refreshControllerRef.current === controller) {
        refreshControllerRef.current = null;
      }
      if (!controller.signal.aborted) {
        setRefreshing(false);
        if (foregroundRefresh) {
          setLoading(false);
        }
      }
    }
  }, []);

  useEffect(() => {
    refresh("initial");
    return () => {
      const controller = refreshControllerRef.current;
      controller?.abort();
      if (controller) {
        refreshControllerRef.current = null;
      }
    };
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      refresh("background");
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [autoRefresh, refresh]);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timer = window.setTimeout(() => setToast(""), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const selectedCall = useMemo(
    () => data.activeCalls.find((call) => call.call_sid === selectedCallSid),
    [data.activeCalls, selectedCallSid]
  );

  useEffect(() => {
    if (!selectedCall) {
      return;
    }
    if (hydratedCorrectionSidRef.current === selectedCall.call_sid) {
      return;
    }
    hydratedCorrectionSidRef.current = selectedCall.call_sid;
    setCorrection({
      category: selectedCall.category || "general",
      urgency: String(selectedCall.urgency ?? 0.5),
      summary: selectedCall.ai_summary || "",
      resolution: selectedCall.adapted_resolution || selectedCall.resolution || "",
      notes: ""
    });
  }, [selectedCall]);

  const waitingQueue = data.queue.filter((entry) => entry.status === "waiting");
  const highHelpAlerts = data.queue.filter((entry) => entry.status === "high_help_alert");
  const availableAgents = data.agents.filter((agent) => agent.is_available);
  const handoverCalls = data.activeCalls.filter((call) => call.phase === "handover_pending");
  const backendHealthy = ["ok", "healthy"].includes(String(data.health?.status || "").toLowerCase());

  const stats = [
    {
      label: "Active calls",
      value: data.activeCalls.length,
      detail: `${handoverCalls.length} waiting for officer`,
      tone: "#111111"
    },
    {
      label: "Queue",
      value: waitingQueue.length,
      detail: `${highHelpAlerts.length} High-Help alerts`,
      tone: "#ff5c5c"
    },
    {
      label: "Officers online",
      value: availableAgents.length,
      detail: `${data.agents.length} total officers`,
      tone: "#22c55e"
    },
    {
      label: "Complaints",
      value: data.complaints.length,
      detail: "structured records",
      tone: "#2dbfad"
    },
    {
      label: "Knowledge",
      value: data.cases.length,
      detail: "resolved cases",
      tone: "#9b59b6"
    },
    {
      label: "Audit events",
      value: data.events.length,
      detail: "latest loaded",
      tone: "#e85d5d"
    },
    {
      label: "Agent turns",
      value: data.agentTraces.length,
      detail: "bounded traces",
      tone: "#4a90d9"
    }
  ];

  function handleDashboardAuthRequired() {
    dashboardKeyRef.current = "";
    window.localStorage.removeItem(DASHBOARD_KEY_STORAGE);
    setAuthRequired(true);
    setAuthError("Dashboard key was rejected. Please enter the correct access key.");
  }

  function submitDashboardKey(event: FormEvent) {
    event.preventDefault();
    const key = authInput.trim();
    if (!key) {
      setAuthError("Dashboard access key is required.");
      return;
    }
    dashboardKeyRef.current = key;
    window.localStorage.setItem(DASHBOARD_KEY_STORAGE, key);
    setAuthError("");
    setAuthRequired(false);
    refresh("manual");
  }

  async function loadTranscript(callSid: string) {
    try {
      const response = await apiGet<AnyRecord>(
        `/api/call-transcript/${callSid}`,
        { transcript: [] },
        { dashboardKey: dashboardKeyRef.current }
      );
      setTranscripts((current) => ({ ...current, [callSid]: response.transcript || [] }));
    } catch (authError) {
      if (authError instanceof DashboardAuthError) {
        handleDashboardAuthRequired();
      }
    }
  }

  async function toggleAgent(agent: AnyRecord) {
    try {
      await apiPost("/api/agent/toggle", {
        agent_id: agent.id,
        available: !agent.is_available
      }, {}, dashboardKeyRef.current);
      setToast(`${agent.name || "Officer"} is now ${agent.is_available ? "busy" : "available"}.`);
      refresh("background");
    } catch (authError) {
      if (authError instanceof DashboardAuthError) {
        handleDashboardAuthRequired();
      }
    }
  }

  async function acceptHandover(call: AnyRecord) {
    const selectedAgent =
      call.handover_context?.selected_agent?.id ||
      call.agent_id ||
      call.handover_context?.ranked_agents?.[0]?.agent_id;
    if (!selectedAgent) {
      setError("No routed officer is available for this handover.");
      return;
    }
    let result: AnyRecord;
    try {
      result = await apiPost<AnyRecord>(`/api/handover/${call.call_sid}/accept`, {
        agent_id: selectedAgent,
        notes: handoverNotes
      }, {}, dashboardKeyRef.current);
    } catch (authError) {
      if (authError instanceof DashboardAuthError) {
        handleDashboardAuthRequired();
      }
      return;
    }
    if (result.status === "ok") {
      setToast("Warm handover accepted and transfer event recorded.");
      setError("");
      setHandoverNotes("");
      refresh("background");
    } else {
      setError(result.detail || result.error || "Handover failed.");
    }
  }

  async function applyCorrection(event: FormEvent) {
    event.preventDefault();
    if (!selectedCall) {
      setError("Select an active call before applying corrections.");
      return;
    }
    let result: AnyRecord;
    try {
      result = await apiPost<AnyRecord>(`/api/calls/${selectedCall.call_sid}/corrections`, {
        ...correction,
        urgency: Number(correction.urgency),
        corrected_by: "dashboard"
      }, {}, dashboardKeyRef.current);
    } catch (authError) {
      if (authError instanceof DashboardAuthError) {
        handleDashboardAuthRequired();
      }
      return;
    }
    if (result.status === "ok") {
      setToast("Correction saved as an audit event.");
      setError("");
      refresh("background");
    } else {
      setError(result.detail || result.error || "Correction failed.");
    }
  }

  async function learnFromCall() {
    if (!selectedCall) {
      setError("Select an active call before adding a knowledge case.");
      return;
    }
    let result: AnyRecord;
    try {
      result = await apiPost<AnyRecord>("/api/resolved-cases/from-call", {
        call_sid: selectedCall.call_sid,
        ...correction,
        urgency: Number(correction.urgency),
        tags: [correction.category, selectedCall.language || "english", "dashboard_corrected"]
      }, {}, dashboardKeyRef.current);
    } catch (authError) {
      if (authError instanceof DashboardAuthError) {
        handleDashboardAuthRequired();
      }
      return;
    }
    if (result.status === "ok") {
      setToast(`Knowledge case added via ${result.source}.`);
      setError("");
      refresh("background");
    } else {
      setError(result.detail || result.error || "Could not add knowledge case.");
    }
  }

  async function runTestPipeline(event: FormEvent) {
    event.preventDefault();
    let result: AnyRecord;
    try {
      result = await apiPost<AnyRecord>("/api/test-pipeline", {
        call_sid: testCallSid,
        text: testText,
        language: testLanguage
      }, {}, dashboardKeyRef.current);
    } catch (authError) {
      if (authError instanceof DashboardAuthError) {
        handleDashboardAuthRequired();
      }
      return;
    }
    setTestResult(result);
    setToast("Test pipeline response received.");
    refresh("background");
  }

  async function initiateCall(event: FormEvent) {
    event.preventDefault();
    const digits = callPhone.replace(/\D/g, "");
    if (digits.length < 7) {
      setCallError("Enter a valid phone number.");
      return;
    }
    const fullPhone = callPhone.startsWith("+") ? callPhone : `${callIsd}${digits}`;
    setCallStatus("calling");
    setCallError("");
    setCallResult(null);
    try {
      const result = await apiPost<AnyRecord>(
        "/api/call-me",
        { phone: fullPhone },
        { status: "error", message: "Backend unreachable" },
        dashboardKeyRef.current
      );
      if (result.status === "calling") {
        setCallStatus("success");
        setCallResult(result);
        setToast(`📞 Sahayak is calling ${fullPhone} — pick up!`);
      } else {
        setCallStatus("error");
        setCallError(responseMessage(result, "Call could not be placed."));
      }
    } catch (authError) {
      if (authError instanceof DashboardAuthError) {
        handleDashboardAuthRequired();
      } else {
        setCallStatus("error");
        setCallError("Unexpected error. Check backend and Twilio credentials.");
      }
    }
  }

  if (authRequired) {
    return (
      <DashboardLogin
        value={authInput}
        onChange={setAuthInput}
        onSubmit={submitDashboardKey}
        error={authError}
      />
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-lockup">
          <img className="brand-logo" src="/sahayak_logo.svg" alt="Sahayak 1092" />
          <div className="brand-meta">
            <div className="eyebrow">Sahayak 1092</div>
            <div className="brand-name">Officer Command Center</div>
          </div>
        </div>
        <div className="top-actions">
          <span className={`status-pill ${backendHealthy ? "" : "offline"}`}>
            <span className="live-dot" />
            {data.health?.status || "offline"}
          </span>
          {lastUpdated && <span className="mono-pill">Updated {lastUpdated}</span>}
          <button
            className={`btn ghost ${autoRefresh ? "toggle-on" : ""}`}
            onClick={() => setAutoRefresh((current) => !current)}
            type="button"
          >
            <Radio size={16} />
            {autoRefresh ? "Live on" : "Live paused"}
          </button>
          <button className="btn primary" onClick={() => refresh("manual")} disabled={refreshing}>
            <RefreshCw className={loading ? "spin" : ""} size={16} />
            {loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </header>

      <section className="hero">
        <div>
          <div className="section-kicker">AI-first emergency response</div>
          <h1 className="hero-title">Every call resolved from one command surface.</h1>
          <p className="hero-copy">
            Monitor live calls, queue pressure, officer availability, Vachan status, Smart
            Similarity matches, complaint creation, warm handovers, and audit trails without
            leaving the dashboard.
          </p>
        </div>
        <aside className="hero-panel">
          <div className="signal-grid">
            <div className="signal-tile">
              <div className="stat-label">Live calls</div>
              <div className="signal-value">{data.activeCalls.length}</div>
              <div className="signal-caption">streaming into Sahayak</div>
            </div>
            <div className="signal-tile">
              <div className="stat-label">Queue alerts</div>
              <div className="signal-value">{highHelpAlerts.length}</div>
              <div className="signal-caption">High-Help watchlist</div>
            </div>
            <div className="signal-tile">
              <div className="stat-label">Vector cases</div>
              <div className="signal-value">{data.cases.length}</div>
              <div className="signal-caption">knowledge assets</div>
            </div>
            <div className="signal-tile">
              <div className="stat-label">Audit loaded</div>
              <div className="signal-value">{data.events.length}</div>
              <div className="signal-caption">latest decisions</div>
            </div>
          </div>
        </aside>
      </section>

      <nav className="nav" aria-label="Dashboard navigation">
        {tabs.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              className={`nav-button ${tab === item.key ? "active" : ""}`}
              onClick={() => setTab(item.key)}
            >
              <Icon size={15} />
              {item.label}
            </button>
          );
        })}
      </nav>

      <section className="metric-grid">
        {stats.map((item) => (
          <MetricCard key={item.label} {...item} />
        ))}
      </section>

      {(toast || error) && (
        <div className={`toast ${error ? "error" : ""}`}>{error || toast}</div>
      )}

      <section className={`workspace${tab === "complaints" ? " workspace-full" : ""}`}>
        <div className="main-stack">
          {(tab === "overview" || tab === "calls") && (
            <ActiveCalls
              calls={data.activeCalls}
              selectedCallSid={selectedCallSid}
              onSelect={setSelectedCallSid}
              onTranscript={loadTranscript}
              onAccept={acceptHandover}
              transcripts={transcripts}
              handoverNotes={handoverNotes}
              setHandoverNotes={setHandoverNotes}
            />
          )}

          {(tab === "overview" || tab === "queue") && <QueuePanel queue={data.queue} />}

          {tab === "officers" && <OfficerPanel agents={data.agents} onToggle={toggleAgent} />}

          {tab === "complaints" && (
            <ComplaintPanel
              complaints={data.complaints}
              callLogs={data.callLogs}
              onViewDetail={setSelectedComplaint}
            />
          )}

          {selectedComplaint && (
            <ComplaintDetailModal
              complaint={selectedComplaint}
              callLogs={data.callLogs}
              onClose={() => setSelectedComplaint(null)}
              dashboardKey={dashboardKeyRef.current}
            />
          )}


          {tab === "knowledge" && <KnowledgePanel cases={data.cases} />}

          {tab === "audit" && (
            <>
              <AgentTracePanel traces={data.agentTraces} />
              <AuditPanel events={data.events} />
            </>
          )}

          {tab === "test" && (
            <TestConsole
              text={testText}
              setText={setTestText}
              language={testLanguage}
              setLanguage={setTestLanguage}
              callSid={testCallSid}
              setCallSid={setTestCallSid}
              result={testResult}
              onSubmit={runTestPipeline}
            />
          )}

          {tab === "call" && (
            <CallMePanel
              phone={callPhone}
              setPhone={setCallPhone}
              isd={callIsd}
              setIsd={setCallIsd}
              status={callStatus}
              result={callResult}
              error={callError}
              onSubmit={initiateCall}
              onReset={() => {
                setCallStatus("idle");
                setCallResult(null);
                setCallError("");
                setCallPhone("");
              }}
            />
          )}
        </div>

        {tab !== "complaints" && (
          <aside className="side-stack">
            <CorrectionPanel
              selectedCall={selectedCall}
              correction={correction}
              setCorrection={setCorrection}
              onApply={applyCorrection}
              onLearn={learnFromCall}
            />
            <HealthPanel health={data.health} />
            <AuditPanel events={data.events.slice(0, 6)} compact />
          </aside>
        )}
      </section>
    </main>
  );
}

function DashboardLogin({
  value,
  onChange,
  onSubmit,
  error
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  error: string;
}) {
  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <img className="auth-logo" src="/sahayak_logo.png" alt="Sahayak 1092" />
        <div>
          <div className="section-kicker">Protected command center</div>
          <h1 className="auth-title">Enter dashboard access key.</h1>
          <p className="section-copy">
            The backend is protected. Use the value from `SAHAYAK_DASHBOARD_API_KEY` in
            `dashboard/.env.local` to unlock this browser session.
          </p>
        </div>
        <form className="form-grid auth-form" onSubmit={onSubmit}>
          <label className="field wide">
            <span className="field-label">Dashboard key</span>
            <input
              className="input mono"
              type="password"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder="Paste dashboard access key"
              autoComplete="current-password"
            />
          </label>
          {error && <div className="toast error wide">{error}</div>}
          <button className="btn primary wide">
            <ShieldCheck size={15} />
            Unlock dashboard
          </button>
        </form>
      </section>
    </main>
  );
}

function ActiveCalls({
  calls,
  selectedCallSid,
  onSelect,
  onTranscript,
  onAccept,
  transcripts,
  handoverNotes,
  setHandoverNotes
}: {
  calls: AnyRecord[];
  selectedCallSid: string;
  onSelect: (sid: string) => void;
  onTranscript: (sid: string) => void;
  onAccept: (call: AnyRecord) => void;
  transcripts: Record<string, AnyRecord[]>;
  handoverNotes: string;
  setHandoverNotes: (value: string) => void;
}) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Live call control</div>
          <h2 className="section-title">Active calls</h2>
          <p className="section-copy">
            Inspect AI summary, Vachan state, similarity, routing context, transcript, and handover.
          </p>
        </div>
        <Badge tone="green">{calls.length} live</Badge>
      </div>

      {calls.length === 0 ? (
        <div className="empty">No active calls right now. The backend is ready for the next demo.</div>
      ) : (
        <div className="grid-two">
          {calls.map((call) => {
            const selected = selectedCallSid === call.call_sid;
            const transcript = transcripts[call.call_sid] || [];
            return (
              <article className="call-card" key={call.call_sid}>
                <div className="call-top">
                  <div>
                    <p className="caller">{call.caller_number || "Unknown caller"}</p>
                    <div className="hash">{compactSid(call.call_sid)}</div>
                  </div>
                  <Badge tone={statusTone(call.phase)}>{call.phase || "collecting"}</Badge>
                </div>
                <p className="summary">{call.ai_summary || "Awaiting caller issue summary."}</p>
                <div className="mini-grid">
                  <Mini label="Language" value={call.language || "unknown"} />
                  <Mini label="Urgency" value={percent(call.urgency)} />
                  <Mini label="Confidence" value={percent(call.confidence)} />
                  <Mini label="Sentiment" value={call.sentiment || "calm"} />
                </div>
                <div className="button-row">
                  <button className="btn primary" onClick={() => onSelect(call.call_sid)}>
                    <Edit3 size={15} />
                    {selected ? "Selected" : "Correct"}
                  </button>
                  <button className="btn ghost" onClick={() => onTranscript(call.call_sid)}>
                    <FileText size={15} />
                    Transcript
                  </button>
                  <button
                    className="btn ghost"
                    onClick={() => onAccept(call)}
                    disabled={call.phase !== "handover_pending"}
                  >
                    <PhoneCall size={15} />
                    Accept handover
                  </button>
                </div>
                {call.phase === "handover_pending" && (
                  <textarea
                    className="textarea"
                    value={handoverNotes}
                    onChange={(event) => setHandoverNotes(event.target.value)}
                    placeholder="Officer notes before accepting handover"
                  />
                )}
                {call.similarity_score && (
                  <Badge tone="teal">Similarity {percent(call.similarity_score)}</Badge>
                )}
                {call.routing_score_breakdown?.score && (
                  <Badge tone="purple">Routing {percent(call.routing_score_breakdown.score)}</Badge>
                )}
                {transcript.length > 0 && (
                  <div className="transcript-box">
                    {transcript.map((turn, index) => (
                      <div key={`${turn.role}-${index}`}>
                        <strong>{turn.role || "turn"}:</strong> {turn.text || ""}
                      </div>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Mini({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="mini" title={detail}>
      <div className="table-label">{label}</div>
      <div className="mini-value">{value}</div>
      {detail && <div className="mini-detail">{detail}</div>}
    </div>
  );
}

function QueuePanel({ queue }: { queue: AnyRecord[] }) {
  const sorted = [...queue].sort((a, b) => Number(a.position || 99) - Number(b.position || 99));
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Surge operations</div>
          <h2 className="section-title">Priority queue and High-Help Alerts</h2>
          <p className="section-copy">
            Queue entries are ranked by urgency, sentiment, confidence, and surge reason.
          </p>
        </div>
        <Badge tone="red">{queue.filter((entry) => entry.status === "high_help_alert").length} alerts</Badge>
      </div>
      {sorted.length === 0 ? (
        <div className="empty">No queue entries loaded.</div>
      ) : (
        <div className="queue-list">
          {sorted.map((entry) => (
            <article
              className={`queue-row ${entry.status === "high_help_alert" ? "alert" : ""}`}
              key={entry.id || entry.call_sid}
            >
              <div className="row-top">
                <div>
                  <div className="caller">{entry.caller_number || "Unknown caller"}</div>
                  <div className="hash">{compactSid(entry.call_sid)}</div>
                </div>
                <Badge tone={statusTone(entry.status)}>{entry.status || "waiting"}</Badge>
              </div>
              <div className="mini-grid">
                <Mini label="Position" value={String(entry.position || "-")} />
                <Mini label="Wait" value={`${entry.estimated_wait_sec ?? 0}s`} />
                <Mini label="Priority" value={percent(entry.priority_score)} />
                <Mini label="Target" value={entry.service_target || "officer"} />
              </div>
              <div className="progress">
                <span style={{ width: percent(entry.priority_score) }} />
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function OfficerPanel({ agents, onToggle }: { agents: AnyRecord[]; onToggle: (agent: AnyRecord) => void }) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Human routing</div>
          <h2 className="section-title">Officers</h2>
          <p className="section-copy">Toggle availability and verify routing fit for demo scenarios.</p>
        </div>
        <Badge tone="green">{agents.filter((agent) => agent.is_available).length} online</Badge>
      </div>
      <div className="agent-list">
        {agents.map((agent) => (
          <article className="agent-row" key={agent.id}>
            <div className="row-top">
              <div>
                <div className="caller">{agent.name || "Officer"}</div>
                <div className="hash">{agent.badge_id || agent.id}</div>
              </div>
              <Badge tone={agent.is_available ? "green" : "red"}>
                {agent.is_available ? "available" : "busy"}
              </Badge>
            </div>
            <p className="summary">
              {(agent.languages || []).join(", ") || "No language data"} /{" "}
              {(agent.specialties || []).join(", ") || "general"}
            </p>
            <div className="button-row">
              <button className="btn primary" onClick={() => onToggle(agent)}>
                <Users size={15} />
                Set {agent.is_available ? "busy" : "available"}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function CorrectionPanel({
  selectedCall,
  correction,
  setCorrection,
  onApply,
  onLearn
}: {
  selectedCall?: AnyRecord;
  correction: CorrectionForm;
  setCorrection: (value: CorrectionForm) => void;
  onApply: (event: FormEvent) => void;
  onLearn: () => void;
}) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Officer correction</div>
          <h2 className="section-title">Correct and learn</h2>
        </div>
        <Badge tone={selectedCall ? "green" : "blue"}>
          {selectedCall ? compactSid(selectedCall.call_sid) : "select call"}
        </Badge>
      </div>
      <form className="form-grid" onSubmit={onApply}>
        <label className="field">
          <span className="field-label">Category</span>
          <select
            className="select"
            value={correction.category}
            onChange={(event) => setCorrection({ ...correction, category: event.target.value })}
          >
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Urgency</span>
          <input
            className="input"
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={correction.urgency}
            onChange={(event) => setCorrection({ ...correction, urgency: event.target.value })}
          />
        </label>
        <label className="field wide">
          <span className="field-label">Summary</span>
          <textarea
            className="textarea"
            value={correction.summary}
            onChange={(event) => setCorrection({ ...correction, summary: event.target.value })}
            placeholder="Corrected officer summary"
          />
        </label>
        <label className="field wide">
          <span className="field-label">Resolution</span>
          <textarea
            className="textarea"
            value={correction.resolution}
            onChange={(event) => setCorrection({ ...correction, resolution: event.target.value })}
            placeholder="Corrected human resolution for future learning"
          />
        </label>
        <label className="field wide">
          <span className="field-label">Notes</span>
          <input
            className="input"
            value={correction.notes}
            onChange={(event) => setCorrection({ ...correction, notes: event.target.value })}
            placeholder="Reason for correction"
          />
        </label>
        <div className="button-row wide">
          <button className="btn primary" disabled={!selectedCall}>
            <CheckCircle2 size={15} />
            Save correction
          </button>
          <button className="btn ghost" type="button" disabled={!selectedCall} onClick={onLearn}>
            <Database size={15} />
            Add to knowledge base
          </button>
        </div>
      </form>
    </section>
  );
}

// ── Complaint status lifecycle ──────────────────────────
const COMPLAINT_STAGES: Array<{ key: string; label: string }> = [
  { key: "registered",   label: "Registered"    },
  { key: "in_progress",  label: "In Progress"   },
  { key: "action_taken", label: "Action Taken"  },
  { key: "resolved",     label: "Resolved"      },
  { key: "closed",       label: "Closed"        },
];

function stageIndex(status?: string): number {
  const idx = COMPLAINT_STAGES.findIndex((s) => s.key === status);
  return idx === -1 ? 0 : idx;
}

function categoryLabel(cat?: string): string {
  const map: Record<string, string> = {
    theft: "Theft / Loss",
    accident: "Accident",
    domestic: "Domestic Violence",
    cyber: "Cyber / Financial Fraud",
    noise: "Noise Disturbance",
    missing_person: "Missing Person",
    suspicious_activity: "Suspicious Activity",
    medical: "Medical Emergency",
    fire: "Fire Emergency",
    traffic: "Traffic Issue",
    harassment: "Harassment",
    civic: "Civic / Municipal",
    general: "General",
  };
  return map[(cat || "").toLowerCase()] || (cat || "General");
}

function urgencyLabel(u?: number): string {
  if (u === undefined || u === null) return "—";
  if (u >= 0.9) return "Critical";
  if (u >= 0.7) return "High";
  if (u >= 0.4) return "Medium";
  return "Low";
}

function urgencyTone(u?: number): string {
  if (u === undefined || u === null) return "";
  if (u >= 0.9) return "red";
  if (u >= 0.7) return "red";
  if (u >= 0.4) return "blue";
  return "teal";
}

function timelineLabel(eventType: string): string {
  const map: Record<string, string> = {
    complaint_registered: "Complaint registered by AI",
    government_payload_created: "Forwarded to government registry",
    status_updated: "Status updated",
    note_added: "Officer note added",
    officer_action: "Officer action recorded",
    complaint_resolved: "Complaint resolved",
  };
  return map[eventType] || eventType.replace(/_/g, " ");
}

function formatTs(iso?: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function ComplaintPanel({
  complaints,
  callLogs,
  onViewDetail,
}: {
  complaints: AnyRecord[];
  callLogs: AnyRecord[];
  onViewDetail: (complaint: AnyRecord) => void;
}) {
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = complaints.filter((c) => {
    const matchStatus = statusFilter === "all" || c.status === statusFilter;
    if (!filter) return matchStatus;
    const s = filter.toLowerCase();
    return matchStatus && (
      (c.reference_id || "").toLowerCase().includes(s) ||
      (c.category || "").toLowerCase().includes(s) ||
      (c.description || "").toLowerCase().includes(s) ||
      (c.caller_number || "").toLowerCase().includes(s)
    );
  });

  const counts = COMPLAINT_STAGES.reduce<Record<string, number>>((acc, st) => {
    acc[st.key] = complaints.filter((c) => c.status === st.key).length;
    return acc;
  }, {});

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Citizen complaints</div>
          <h2 className="section-title">Complaint Registry</h2>
          <p className="section-copy">
            All complaints registered by the AI system. Click a complaint to view details, take
            action, or mark it resolved.
          </p>
        </div>
        <Badge tone="teal">{complaints.length} total</Badge>
      </div>

      {/* Stage summary bar */}
      <div className="complaint-stage-bar">
        {COMPLAINT_STAGES.map((st) => (
          <button
            key={st.key}
            className={`stage-chip ${statusFilter === st.key ? "active" : ""}`}
            onClick={() => setStatusFilter((prev) => prev === st.key ? "all" : st.key)}
          >
            <span className="stage-chip-label">{st.label}</span>
            <span className="stage-chip-count">{counts[st.key] ?? 0}</span>
          </button>
        ))}
        {statusFilter !== "all" && (
          <button className="stage-chip clear" onClick={() => setStatusFilter("all")}>
            Show all
          </button>
        )}
      </div>

      {/* Search */}
      <div className="complaint-search">
        <input
          className="input"
          placeholder="Search by reference ID, category, or caller number"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          {complaints.length === 0
            ? "No complaints registered yet. They appear here when Sahayak AI resolves a call."
            : "No complaints match the current filter."}
        </div>
      ) : (
        <div className="complaint-table-wrap">
          <table className="complaint-table">
            <thead>
              <tr>
                <th>Reference ID</th>
                <th>Category</th>
                <th>Caller</th>
                <th>Description</th>
                <th>Urgency</th>
                <th>Stage</th>
                <th>Registered</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((complaint) => {
                const log = callLogs.find((l) => l.call_sid === complaint.call_sid);
                const caller = complaint.caller_number || log?.caller_number || "Unknown";
                const urgency = complaint.urgency ?? log?.urgency;
                const stageIdx = stageIndex(complaint.status);
                return (
                  <tr
                    key={complaint.id || complaint.reference_id}
                    className="complaint-tr"
                    onClick={() => onViewDetail({ ...complaint, _call_log: log })}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <span className="hash" style={{ fontSize: 11 }}>
                        {complaint.reference_id || "—"}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontWeight: 700, fontSize: 13 }}>
                        {categoryLabel(complaint.category)}
                      </span>
                    </td>
                    <td>
                      <span className="complaint-caller">{caller}</span>
                    </td>
                    <td className="complaint-desc">
                      {(complaint.description || "—").slice(0, 72)}
                      {(complaint.description || "").length > 72 ? "…" : ""}
                    </td>
                    <td>
                      <Badge tone={urgencyTone(urgency)}>{urgencyLabel(urgency)}</Badge>
                    </td>
                    <td>
                      <div className="stage-pill-row">
                        {COMPLAINT_STAGES.slice(0, 4).map((st, i) => (
                          <div
                            key={st.key}
                            className={`stage-dot ${i <= stageIdx ? "done" : ""} ${complaint.status === st.key ? "current" : ""}`}
                            title={st.label}
                          />
                        ))}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3 }}>
                        {COMPLAINT_STAGES.find((s) => s.key === complaint.status)?.label || "Registered"}
                      </div>
                    </td>
                    <td style={{ whiteSpace: "nowrap", fontSize: 11, color: "var(--text-secondary)" }}>
                      {formatTs(complaint.created_at)}
                    </td>
                    <td>
                      <button
                        className="btn ghost"
                        style={{ fontSize: 12, whiteSpace: "nowrap" }}
                        onClick={(e) => { e.stopPropagation(); onViewDetail({ ...complaint, _call_log: log }); }}
                      >
                        <Eye size={13} />
                        View
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ComplaintDetailModal({
  complaint: initialComplaint,
  callLogs,
  onClose,
  dashboardKey,
}: {
  complaint: AnyRecord;
  callLogs: AnyRecord[];
  onClose: () => void;
  dashboardKey: string;
}) {
  const [complaint, setComplaint] = useState<AnyRecord>(initialComplaint);
  const [timeline, setTimeline] = useState<AnyRecord[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [actionNote, setActionNote] = useState("");
  const [selectedStatus, setSelectedStatus] = useState(complaint.status || "registered");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [noteText, setNoteText] = useState("");
  const [noteSubmitting, setNoteSubmitting] = useState(false);

  const log = complaint._call_log || callLogs.find((l) => l.call_sid === complaint.call_sid);
  const urgency = complaint.urgency ?? log?.urgency;
  const stageIdx = stageIndex(complaint.status);

  // Load timeline on mount
  useEffect(() => {
    if (!complaint.reference_id) return;
    setTimelineLoading(true);
    apiGet<AnyRecord>(
      `/api/complaints/${complaint.reference_id}/timeline`,
      { timeline: [] },
      { dashboardKey }
    ).then((r) => {
      setTimeline((r.timeline as AnyRecord[]) || []);
      setTimelineLoading(false);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [complaint.reference_id]);

  async function saveAction() {
    if (!selectedStatus && !actionNote) return;
    setSaving(true);
    setSaveMsg("");
    const body: AnyRecord = { officer: "dashboard" };
    if (selectedStatus !== complaint.status) body.status = selectedStatus;
    if (actionNote.trim()) body.action_note = actionNote.trim();

    try {
      const result = await fetch(`/api/sahayak/api/complaints/${complaint.reference_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "x-sahayak-dashboard-key": dashboardKey },
        body: JSON.stringify(body),
      }).then((r) => r.json());

      if (result.status === "ok") {
        setComplaint((prev) => ({ ...prev, ...body, status: selectedStatus }));
        setActionNote("");
        setSaveMsg("Action saved successfully.");
        // refresh timeline
        const tl = await apiGet<AnyRecord>(
          `/api/complaints/${complaint.reference_id}/timeline`,
          { timeline: [] },
          { dashboardKey }
        );
        setTimeline((tl.timeline as AnyRecord[]) || []);
      } else {
        setSaveMsg("Failed to save action.");
      }
    } catch {
      setSaveMsg("Network error. Please try again.");
    }
    setSaving(false);
  }

  async function submitNote() {
    if (!noteText.trim()) return;
    setNoteSubmitting(true);
    try {
      await fetch(`/api/sahayak/api/complaints/${complaint.reference_id}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-sahayak-dashboard-key": dashboardKey },
        body: JSON.stringify({ note: noteText.trim(), officer: "dashboard" }),
      });
      setNoteText("");
      const tl = await apiGet<AnyRecord>(
        `/api/complaints/${complaint.reference_id}/timeline`,
        { timeline: [] },
        { dashboardKey }
      );
      setTimeline((tl.timeline as AnyRecord[]) || []);
    } catch {}
    setNoteSubmitting(false);
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-panel">

        {/* Header */}
        <div className="modal-header">
          <div>
            <div className="section-kicker">Complaint Record</div>
            <h2 className="section-title" style={{ marginTop: 4 }}>
              {complaint.reference_id || "—"}
            </h2>
            <div style={{ marginTop: 6, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Badge tone={urgencyTone(urgency)}>{urgencyLabel(urgency)} urgency</Badge>
              <Badge tone={statusTone(complaint.status)}>
                {COMPLAINT_STAGES.find((s) => s.key === complaint.status)?.label || "Registered"}
              </Badge>
              <span style={{ fontSize: 12, color: "var(--text-secondary)", alignSelf: "center" }}>
                {categoryLabel(complaint.category)}
              </span>
            </div>
          </div>
          <button className="btn ghost" onClick={onClose} style={{ padding: "0 10px", minHeight: 34, flexShrink: 0 }}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">

          {/* Progress tracker */}
          <div className="modal-section">
            <div className="modal-section-title">Current Stage</div>
            <div className="complaint-progress-track">
              {COMPLAINT_STAGES.map((st, i) => (
                <div key={st.key} className="progress-step">
                  <div className={`progress-node ${i < stageIdx ? "done" : i === stageIdx ? "active" : "pending"}`}>
                    {i < stageIdx ? <CheckCircle2 size={14} /> : i + 1}
                  </div>
                  <div className={`progress-label ${i === stageIdx ? "active-label" : ""}`}>{st.label}</div>
                  {i < COMPLAINT_STAGES.length - 1 && (
                    <div className={`progress-line ${i < stageIdx ? "done" : ""}`} />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Complaint details */}
          <div className="modal-section">
            <div className="modal-section-title">Complaint Details</div>
            <div className="detail-grid">
              <div className="detail-item">
                <div className="detail-label">Caller Number</div>
                <div className="detail-value">{complaint.caller_number || log?.caller_number || "Unknown"}</div>
              </div>
              <div className="detail-item">
                <div className="detail-label">Category</div>
                <div className="detail-value">{categoryLabel(complaint.category)}</div>
              </div>
              <div className="detail-item">
                <div className="detail-label">Language</div>
                <div className="detail-value">{complaint.language || log?.language || "—"}</div>
              </div>
              <div className="detail-item">
                <div className="detail-label">Registered On</div>
                <div className="detail-value">{formatTs(complaint.created_at)}</div>
              </div>
              {complaint.location && (
                <div className="detail-item wide">
                  <div className="detail-label">Location</div>
                  <div className="detail-value">{complaint.location}</div>
                </div>
              )}
            </div>
            <div className="modal-text-block" style={{ marginTop: 10 }}>
              <div className="detail-label" style={{ marginBottom: 5 }}>Description</div>
              {complaint.description || "No description recorded."}
            </div>
          </div>

          {/* AI Summary */}
          {(log?.ai_summary || log?.adapted_resolution) && (
            <div className="modal-section">
              <div className="modal-section-title">AI Assessment</div>
              <div className="detail-grid">
                <div className="detail-item">
                  <div className="detail-label">Sentiment</div>
                  <div className="detail-value">{log?.sentiment || "—"}</div>
                </div>
                <div className="detail-item">
                  <div className="detail-label">Confidence</div>
                  <div className="detail-value">{log?.confidence !== undefined ? percent(log.confidence) : "—"}</div>
                </div>
                <div className="detail-item">
                  <div className="detail-label">AI Outcome</div>
                  <div className="detail-value">{log?.outcome || "—"}</div>
                </div>
              </div>
              {log?.ai_summary && (
                <div className="modal-text-block" style={{ marginTop: 10 }}>
                  <div className="detail-label" style={{ marginBottom: 5 }}>AI Summary</div>
                  {log.ai_summary}
                </div>
              )}
              {log?.adapted_resolution && (
                <div className="modal-text-block" style={{ marginTop: 8 }}>
                  <div className="detail-label" style={{ marginBottom: 5 }}>Suggested Resolution</div>
                  {log.adapted_resolution}
                </div>
              )}
            </div>
          )}

          {/* Conversation */}
          {log?.transcript && Array.isArray(log.transcript) && log.transcript.length > 0 && (
            <div className="modal-section">
              <div className="modal-section-title">Caller Conversation</div>
              <div className="transcript-box" style={{ maxHeight: 200 }}>
                {log.transcript.map((turn: AnyRecord, i: number) => (
                  <div
                    key={i}
                    className={`convo-turn ${turn.role === "ai" || turn.role === "sahayak" ? "ai-turn" : "caller-turn"}`}
                  >
                    <span className="convo-role">
                      {turn.role === "ai" || turn.role === "sahayak" ? "Sahayak AI" : "Caller"}
                    </span>
                    {turn.text || ""}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timeline */}
          <div className="modal-section">
            <div className="modal-section-title">Activity Timeline</div>
            {timelineLoading ? (
              <div className="detail-label">Loading timeline…</div>
            ) : timeline.length === 0 ? (
              <div className="empty" style={{ padding: "14px 16px" }}>No activity recorded yet.</div>
            ) : (
              <div className="complaint-timeline">
                {[...timeline].sort((a, b) => (a.created_at || "").localeCompare(b.created_at || "")).map((ev, i) => (
                  <div key={ev.id || i} className="timeline-row">
                    <div className="timeline-dot" />
                    <div className="timeline-content">
                      <div className="timeline-event">{timelineLabel(ev.event_type)}</div>
                      {ev.payload?.note && (
                        <div className="timeline-note">{ev.payload.note}</div>
                      )}
                      {ev.payload?.action_note && (
                        <div className="timeline-note">{ev.payload.action_note}</div>
                      )}
                      {ev.payload?.status && ev.event_type === "status_updated" && (
                        <div className="timeline-note">
                          Status changed to: <strong>{COMPLAINT_STAGES.find((s) => s.key === ev.payload.status)?.label || ev.payload.status}</strong>
                        </div>
                      )}
                      {ev.payload?.officer && ev.payload.officer !== "dashboard" && (
                        <div className="timeline-meta">by {ev.payload.officer}</div>
                      )}
                      <div className="timeline-meta">{formatTs(ev.created_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Add note */}
            <div className="action-note-row">
              <textarea
                className="textarea"
                placeholder="Add an officer note (e.g. 'Dispatched patrol unit to location')"
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                style={{ minHeight: 72 }}
              />
              <button
                className="btn ghost"
                onClick={submitNote}
                disabled={!noteText.trim() || noteSubmitting}
                style={{ alignSelf: "flex-end" }}
              >
                <Send size={14} />
                {noteSubmitting ? "Adding…" : "Add Note"}
              </button>
            </div>
          </div>

          {/* Action panel */}
          <div className="modal-section action-panel">
            <div className="modal-section-title">Take Action</div>
            <div className="action-form">
              <div className="field">
                <span className="field-label">Update Status</span>
                <select
                  className="select"
                  value={selectedStatus}
                  onChange={(e) => setSelectedStatus(e.target.value)}
                >
                  {COMPLAINT_STAGES.map((st) => (
                    <option key={st.key} value={st.key}>{st.label}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <span className="field-label">Action Taken (optional note)</span>
                <input
                  className="input"
                  placeholder="Describe the action taken"
                  value={actionNote}
                  onChange={(e) => setActionNote(e.target.value)}
                />
              </div>
            </div>
            <div className="button-row" style={{ marginTop: 10 }}>
              <button
                className="btn primary"
                onClick={saveAction}
                disabled={saving || (selectedStatus === complaint.status && !actionNote.trim())}
              >
                <CheckCircle2 size={15} />
                {saving ? "Saving…" : "Save Action"}
              </button>
              {complaint.status !== "resolved" && (
                <button
                  className="btn ghost"
                  onClick={() => { setSelectedStatus("resolved"); setTimeout(saveAction, 0); }}
                  disabled={saving}
                >
                  <BadgeCheck size={15} />
                  Mark Resolved
                </button>
              )}
            </div>
            {saveMsg && (
              <div className={`toast ${saveMsg.includes("Failed") || saveMsg.includes("error") ? "error" : ""}`} style={{ marginTop: 10 }}>
                {saveMsg}
              </div>
            )}
          </div>

          {/* Reference footer */}
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, color: "var(--text-secondary)", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
            {complaint.call_sid && <span>Call SID: <span className="hash">{complaint.call_sid}</span></span>}
            {complaint.id && <span>Record ID: <span className="hash">{complaint.id}</span></span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function KnowledgePanel({ cases }: { cases: AnyRecord[] }) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Smart Similarity</div>
          <h2 className="section-title">Knowledge base</h2>
        </div>
        <Badge tone="purple">{cases.length} cases</Badge>
      </div>
      <div className="case-list">
        {cases.map((item, index) => (
          <article className="case-row" key={item.id || `${item.category}-${index}`}>
            <div className="row-top">
              <div>
                <div className="caller">{item.category || "general"}</div>
                <div className="hash">{item.id || item.source_call_sid || "local-demo"}</div>
              </div>
              <Badge tone="teal">{item.language || "unknown"}</Badge>
            </div>
            <p className="summary">{item.summary}</p>
            <p className="summary">
              <strong>Resolution:</strong> {item.resolution}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function AuditPanel({ events, compact = false }: { events: AnyRecord[]; compact?: boolean }) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Audit trail</div>
          <h2 className="section-title">{compact ? "Recent audit" : "Decision audit"}</h2>
        </div>
        <Badge tone="red">{events.length} events</Badge>
      </div>
      <div className="event-list">
        {events.length === 0 ? (
          <div className="empty">No events loaded.</div>
        ) : (
          events.map((event) => (
            <article className="event-row" key={event.id || `${event.event_type}-${event.created_at}`}>
              <div className="event-name">
                <Network size={15} color="#e85d5d" />
                {event.event_type}
              </div>
              <div className="hash">{compactSid(event.call_sid)}</div>
              {!compact && (
                <pre className="json-block">{JSON.stringify(event.payload || {}, null, 2)}</pre>
              )}
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function AgentTracePanel({ traces }: { traces: AnyRecord[] }) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Agent runtime</div>
          <h2 className="section-title">Bounded agent traces</h2>
          <p className="section-copy">
            Each trace shows what Sahayak observed, which tools it used, the final action, and why
            the safety policy allowed or blocked autonomy.
          </p>
        </div>
        <Badge tone="blue">{traces.length} turns</Badge>
      </div>
      <div className="event-list">
        {traces.length === 0 ? (
          <div className="empty">No agent traces yet. Run a test call to create one.</div>
        ) : (
          traces.map((event) => {
            const trace = event.payload || {};
            const toolCalls = trace.tool_calls || [];
            return (
              <article className="event-row" key={trace.trace_id || event.id}>
                <div className="row-top">
                  <div>
                    <div className="event-name">
                      <Network size={15} color="#4a90d9" />
                      {trace.final_action || "continue"} / {trace.final_phase || "unknown"}
                    </div>
                    <div className="hash">{trace.trace_id || compactSid(event.call_sid)}</div>
                  </div>
                  <Badge tone="blue">{trace.channel || "agent"}</Badge>
                </div>
                <p className="summary">{trace.observed_text || "No observed text captured."}</p>
                <div className="button-row">
                  {toolCalls.slice(0, 8).map((tool: AnyRecord, index: number) => (
                    <Badge tone={tool.name === "evaluate_safety_policy" ? "red" : "teal"} key={`${tool.name}-${index}`}>
                      {tool.name}
                    </Badge>
                  ))}
                </div>
                {(trace.safety_notes || []).length > 0 && (
                  <div className="trace-note">
                    {(trace.safety_notes || []).map((note: string, index: number) => (
                      <div key={`${note}-${index}`}>{note}</div>
                    ))}
                  </div>
                )}
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

function HealthPanel({ health }: { health: AnyRecord | null }) {
  const persistence = health?.persistence || {};
  const voice = health?.voice || {};
  const supabase = persistence.supabase || {};
  const vectorAvailable = persistence.vector_db?.available;
  const redis = persistence.redis || {};
  const supabaseLabel = !supabase.configured
    ? "local"
    : supabase.available === false
      ? "blocked"
      : supabase.key_role === "anon"
        ? "anon key"
        : "configured";
  const redisLabel = redis.available ? "available" : redis.configured ? "unavailable" : "local";
  const vectorLabel =
    vectorAvailable === true
      ? "ready"
      : vectorAvailable === "not_probed"
        ? "configured"
        : persistence.vector_db?.configured
          ? "configured"
          : "local";
  const vectorDetail =
    vectorAvailable === true
      ? "pgvector search tested"
      : persistence.vector_db?.configured
        ? "pgvector configured"
        : "using local fallback";
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">System health</div>
          <h2 className="section-title">Backend</h2>
        </div>
        <Badge tone={statusTone(health?.status)}>{health?.status || "offline"}</Badge>
      </div>
      <div className="mini-grid">
        <Mini label="Active" value={String(health?.active_calls || 0)} />
        <Mini label="Current STT" value={voice.stt?.provider || "none"} />
        <Mini label="Current TTS" value={voice.tts?.provider || "none"} />
        <Mini label="Supabase" value={supabaseLabel} />
        <Mini label="Redis" value={redisLabel} />
        <Mini label="Vector" value={vectorLabel} detail={vectorDetail} />
      </div>
    </section>
  );
}

function TestConsole({
  text,
  setText,
  language,
  setLanguage,
  callSid,
  setCallSid,
  result,
  onSubmit
}: {
  text: string;
  setText: (value: string) => void;
  language: string;
  setLanguage: (value: string) => void;
  callSid: string;
  setCallSid: (value: string) => void;
  result: AnyRecord | null;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">No-phone demo</div>
          <h2 className="section-title">Test console</h2>
          <p className="section-copy">
            Run the exact decision pipeline without Twilio. Reuse the call SID for Vachan.
          </p>
        </div>
        <Badge tone="blue">
          <Mic size={13} />
          text mode
        </Badge>
      </div>
      <form className="test-console" onSubmit={onSubmit}>
        <label className="field">
          <span className="field-label">Call SID</span>
          <input className="input mono" value={callSid} onChange={(event) => setCallSid(event.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">Language</span>
          <select className="select" value={language} onChange={(event) => setLanguage(event.target.value)}>
            <option value="english">english</option>
            <option value="hindi">hindi</option>
            <option value="kannada">kannada</option>
          </select>
        </label>
        <label className="field">
          <span className="field-label">Caller input</span>
          <textarea className="textarea" value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <button className="btn primary">
          <Send size={15} />
          Send to Sahayak
        </button>
        {result?.agent_trace && <AgentTraceSummary trace={result.agent_trace} />}
        {result && <pre className="json-block">{JSON.stringify(result, null, 2)}</pre>}
      </form>
    </section>
  );
}

function AgentTraceSummary({ trace }: { trace: AnyRecord }) {
  const toolCalls = trace.tool_calls || [];
  return (
    <div className="trace-summary">
      <div className="row-top">
        <div>
          <div className="section-kicker">Agent trace</div>
          <div className="caller">{trace.final_action || "continue"} / {trace.final_phase || "unknown"}</div>
        </div>
        <Badge tone="blue">{trace.channel || "api_test"}</Badge>
      </div>
      <div className="button-row">
        {toolCalls.slice(0, 10).map((tool: AnyRecord, index: number) => (
          <Badge tone={tool.name === "evaluate_safety_policy" ? "red" : "teal"} key={`${tool.name}-${index}`}>
            {tool.name}
          </Badge>
        ))}
      </div>
      {(trace.safety_notes || []).length > 0 && (
        <div className="trace-note">
          {(trace.safety_notes || []).map((note: string, index: number) => (
            <div key={`${note}-${index}`}>{note}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── ISD country codes ───────────────────────────────────
const ISD_CODES = [
  { code: "+91", label: "🇮🇳 IN +91" },
  { code: "+1",  label: "🇺🇸 US +1" },
  { code: "+44", label: "🇬🇧 UK +44" },
  { code: "+971", label: "🇦🇪 UAE +971" },
  { code: "+65", label: "🇸🇬 SG +65" },
  { code: "+61", label: "🇦🇺 AU +61" },
  { code: "+49", label: "🇩🇪 DE +49" },
  { code: "+81", label: "🇯🇵 JP +81" },
  { code: "+86", label: "🇨🇳 CN +86" },
];

function CallMePanel({
  phone,
  setPhone,
  isd,
  setIsd,
  status,
  result,
  error,
  onSubmit,
  onReset
}: {
  phone: string;
  setPhone: (v: string) => void;
  isd: string;
  setIsd: (v: string) => void;
  status: "idle" | "calling" | "success" | "error";
  result: AnyRecord | null;
  error: string;
  onSubmit: (event: FormEvent) => void;
  onReset: () => void;
}) {
  const isCalling = status === "calling";

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Outbound via Twilio</div>
          <h2 className="section-title">Call Me</h2>
          <p className="section-copy">
            Sahayak calls the citizen — no ISD recharge needed on their phone.
          </p>
        </div>
        <Badge tone={status === "success" ? "green" : status === "error" ? "red" : status === "calling" ? "blue" : "purple"}>
          <PhoneOutgoing size={13} />
          {status === "idle" ? "ready" : status}
        </Badge>
      </div>

      {/* Info box */}
      <div className="callme-info">
        <Info size={15} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>Why this tab?</strong> Twilio&apos;s outbound calling requires an ISD-enabled
          balance on the Twilio account — <em>not</em> on the recipient&apos;s phone. Enter any
          number below and Sahayak calls them from <code>+1 866 621 2451</code>. The recipient
          just picks up normally.
        </div>
      </div>

      {status === "success" && result ? (
        <div className="callme-success">
          <div className="callme-success-icon">📞</div>
          <div className="callme-success-body">
            <div className="caller" style={{ fontSize: "1.1rem" }}>
              Sahayak is calling {result.to}
            </div>
            <div className="summary">{result.message}</div>
            <div className="mini-grid" style={{ marginTop: 12 }}>
              <Mini label="From" value={result.from || "+1 866 621 2451"} />
              <Mini label="To" value={result.to || phone} />
              <Mini label="Call SID" value={result.call_sid ? result.call_sid.slice(0, 12) + "…" : "—"} />
            </div>
          </div>
          <button className="btn ghost" type="button" onClick={onReset} style={{ alignSelf: "flex-start" }}>
            <PhoneOutgoing size={15} />
            New call
          </button>
        </div>
      ) : (
        <form className="form-grid" onSubmit={onSubmit}>
          <label className="field">
            <span className="field-label">Country / ISD code</span>
            <select
              className="select"
              value={isd}
              onChange={(e) => setIsd(e.target.value)}
              disabled={isCalling}
            >
              {ISD_CODES.map((c) => (
                <option key={c.code} value={c.code}>{c.label}</option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field-label">Phone number</span>
            <input
              className="input mono"
              type="tel"
              placeholder="9876543210"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={isCalling}
              autoComplete="tel"
            />
          </label>

          <div className="callme-preview">
            Will dial: <strong>{phone ? (phone.startsWith("+") ? phone : `${isd}${phone.replace(/\D/g, "")}`) : `${isd}…`}</strong>
          </div>

          {error && <div className="toast error wide">{error}</div>}

          <div className="button-row wide">
            <button
              className={`btn primary ${isCalling ? "calling-pulse" : ""}`}
              disabled={isCalling}
            >
              {isCalling ? (
                <><RefreshCw size={15} className="spin" /> Calling…</>
              ) : (
                <><PhoneOutgoing size={15} /> Call this number</>  
              )}
            </button>
          </div>
        </form>
      )}

      {/* How it works */}
      <div className="callme-steps">
        <div className="section-kicker" style={{ marginBottom: 8 }}>How it works</div>
        <ol className="callme-ol">
          <li>Enter the target phone number and click <strong>Call this number</strong>.</li>
          <li>Twilio deducts from the <em>Sahayak Twilio balance</em> (ISD-enabled) — the recipient pays nothing.</li>
          <li>Sahayak&apos;s AI answers the moment they pick up, just like an inbound 1092 call.</li>
          <li>The call appears live in the <strong>Live Calls</strong> tab within seconds.</li>
        </ol>
      </div>
    </section>
  );
}
