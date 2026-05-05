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
  Mic,
  Network,
  PhoneCall,
  Radio,
  RefreshCw,
  Send,
  ShieldCheck,
  Users
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

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
  | "test";

const API_BASE = "/api/sahayak";

const emptyData: DashboardData = {
  health: null,
  activeCalls: [],
  callLogs: [],
  agents: [],
  queue: [],
  complaints: [],
  cases: [],
  events: []
};

const tabs: Array<{ key: TabKey; label: string; icon: typeof Activity }> = [
  { key: "overview", label: "Overview", icon: Activity },
  { key: "calls", label: "Live Calls", icon: PhoneCall },
  { key: "queue", label: "Queue", icon: Radio },
  { key: "officers", label: "Officers", icon: Users },
  { key: "complaints", label: "Complaints", icon: FileText },
  { key: "knowledge", label: "Knowledge", icon: BookOpen },
  { key: "audit", label: "Audit", icon: History },
  { key: "test", label: "Test Console", icon: Send }
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
  "traffic"
];

async function apiGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

async function apiPost<T>(path: string, body: AnyRecord, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    return (await response.json()) as T;
  } catch {
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
  if (status.includes("resolved") || status.includes("available") || status.includes("ok")) {
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

  const refresh = useCallback(async () => {
    setLoading(true);
    const [
      health,
      active,
      logs,
      agents,
      queue,
      complaints,
      cases,
      events
    ] = await Promise.all([
      apiGet<AnyRecord | null>("/health", null),
      apiGet<AnyRecord>("/api/active-calls", { active_calls: [] }),
      apiGet<AnyRecord>("/api/call-logs", { call_logs: [] }),
      apiGet<AnyRecord>("/api/agents", { agents: [] }),
      apiGet<AnyRecord>("/api/queue?include_inactive=true&limit=50", { queue: [] }),
      apiGet<AnyRecord>("/api/complaints", { complaints: [] }),
      apiGet<AnyRecord>("/api/resolved-cases", { cases: [] }),
      apiGet<AnyRecord>("/api/call-events?limit=80", { events: [] })
    ]);

    setData({
      health,
      activeCalls: active.active_calls || [],
      callLogs: logs.call_logs || [],
      agents: agents.agents || [],
      queue: queue.queue || [],
      complaints: complaints.complaints || [],
      cases: cases.cases || [],
      events: events.events || []
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 8000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const selectedCall = useMemo(
    () => data.activeCalls.find((call) => call.call_sid === selectedCallSid),
    [data.activeCalls, selectedCallSid]
  );

  useEffect(() => {
    if (!selectedCall) {
      return;
    }
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
    }
  ];

  async function loadTranscript(callSid: string) {
    const response = await apiGet<AnyRecord>(`/api/call-transcript/${callSid}`, { transcript: [] });
    setTranscripts((current) => ({ ...current, [callSid]: response.transcript || [] }));
  }

  async function toggleAgent(agent: AnyRecord) {
    await apiPost("/api/agent/toggle", {
      agent_id: agent.id,
      available: !agent.is_available
    }, {});
    setToast(`${agent.name || "Officer"} is now ${agent.is_available ? "busy" : "available"}.`);
    refresh();
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
    const result = await apiPost<AnyRecord>(`/api/handover/${call.call_sid}/accept`, {
      agent_id: selectedAgent,
      notes: handoverNotes
    }, {});
    if (result.status === "ok") {
      setToast("Warm handover accepted and transfer event recorded.");
      setError("");
      setHandoverNotes("");
      refresh();
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
    const result = await apiPost<AnyRecord>(`/api/calls/${selectedCall.call_sid}/corrections`, {
      ...correction,
      urgency: Number(correction.urgency),
      corrected_by: "dashboard"
    }, {});
    if (result.status === "ok") {
      setToast("Correction saved as an audit event.");
      setError("");
      refresh();
    } else {
      setError(result.detail || result.error || "Correction failed.");
    }
  }

  async function learnFromCall() {
    if (!selectedCall) {
      setError("Select an active call before adding a knowledge case.");
      return;
    }
    const result = await apiPost<AnyRecord>("/api/resolved-cases/from-call", {
      call_sid: selectedCall.call_sid,
      ...correction,
      urgency: Number(correction.urgency),
      tags: [correction.category, selectedCall.language || "english", "dashboard_corrected"]
    }, {});
    if (result.status === "ok") {
      setToast(`Knowledge case added via ${result.source}.`);
      setError("");
      refresh();
    } else {
      setError(result.detail || result.error || "Could not add knowledge case.");
    }
  }

  async function runTestPipeline(event: FormEvent) {
    event.preventDefault();
    const result = await apiPost<AnyRecord>("/api/test-pipeline", {
      call_sid: testCallSid,
      text: testText,
      language: testLanguage
    }, {});
    setTestResult(result);
    setToast("Test pipeline response received.");
    refresh();
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">
            <ShieldCheck size={22} />
          </div>
          <div className="brand-meta">
            <div className="eyebrow">Sahayak 1092</div>
            <div className="brand-name">Officer Command Center</div>
          </div>
        </div>
        <div className="top-actions">
          <span className="status-pill">
            <span className="live-dot" />
            {data.health?.status || "offline"}
          </span>
          <button className="btn primary" onClick={refresh} disabled={loading}>
            <RefreshCw size={16} />
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

      <section className="workspace">
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

          {tab === "complaints" && <ComplaintPanel complaints={data.complaints} />}

          {tab === "knowledge" && <KnowledgePanel cases={data.cases} />}

          {tab === "audit" && <AuditPanel events={data.events} />}

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
        </div>

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

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="mini">
      <div className="table-label">{label}</div>
      <div className="mini-value">{value}</div>
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

function ComplaintPanel({ complaints }: { complaints: AnyRecord[] }) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <div className="section-kicker">Citizen actions</div>
          <h2 className="section-title">Complaints</h2>
        </div>
        <Badge tone="teal">{complaints.length} records</Badge>
      </div>
      <div className="complaint-list">
        {complaints.map((complaint) => (
          <article className="complaint-row" key={complaint.id || complaint.reference_id}>
            <div className="row-top">
              <div>
                <div className="caller">{complaint.category || "general"}</div>
                <div className="hash">{complaint.reference_id}</div>
              </div>
              <Badge tone={statusTone(complaint.status)}>{complaint.status || "registered"}</Badge>
            </div>
            <p className="summary">{complaint.description || "No description available."}</p>
          </article>
        ))}
      </div>
    </section>
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

function HealthPanel({ health }: { health: AnyRecord | null }) {
  const persistence = health?.persistence || {};
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
        <Mini label="Supabase" value={String(persistence.supabase_configured || false)} />
        <Mini label="Redis" value={String(persistence.redis?.available || false)} />
        <Mini label="Vector" value={String(persistence.vector_db?.available || false)} />
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
        {result && <pre className="json-block">{JSON.stringify(result, null, 2)}</pre>}
      </form>
    </section>
  );
}
