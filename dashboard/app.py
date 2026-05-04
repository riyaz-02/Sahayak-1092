"""
Sahayak 1092 – Agent Dashboard (Streamlit)
===========================================
Live dashboard for human officers / supervisors.

Features:
  • Real-time active calls with transcript
  • AI summary, sentiment badges, urgency meters
  • Take Call / Accept Handover buttons
  • One-click correction buttons for AI responses
  • Call history with filters
  • Agent management panel
  • Knowledge base viewer
  • Complaints tracker
"""

import os
import time
from datetime import datetime

import requests
import streamlit as st

# ── Config ──────────────────────────────────────
API_BASE = os.getenv("SAHAYAK_API_URL", "http://localhost:8000")

# ── Page Config ─────────────────────────────────
st.set_page_config(
    page_title="Sahayak 1092 – Command Center",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──────────────────────────────────
st.markdown("""
<style>
    /* ── Global ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* ── Header ── */
    .header-container {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 1.5rem 2rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255,255,255,0.1);
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .header-title {
        color: #fff;
        font-size: 2rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .header-subtitle {
        color: rgba(255,255,255,0.7);
        font-size: 0.9rem;
        margin-top: 4px;
    }
    .header-stats {
        display: flex;
        gap: 2rem;
        margin-top: 1rem;
    }
    .stat-box {
        background: rgba(255,255,255,0.08);
        backdrop-filter: blur(10px);
        padding: 0.8rem 1.4rem;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .stat-value {
        color: #fff;
        font-size: 1.8rem;
        font-weight: 700;
    }
    .stat-label {
        color: rgba(255,255,255,0.6);
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    /* ── Cards ── */
    .call-card {
        background: linear-gradient(145deg, #1a1a2e, #16213e);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        transition: all 0.3s ease;
    }
    .call-card:hover {
        border-color: rgba(99, 102, 241, 0.4);
        box-shadow: 0 4px 30px rgba(99, 102, 241, 0.15);
    }

    /* ── Badges ── */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-calm { background: #064e3b; color: #6ee7b7; }
    .badge-anxious { background: #78350f; color: #fcd34d; }
    .badge-distressed { background: #7c2d12; color: #fb923c; }
    .badge-angry { background: #7f1d1d; color: #fca5a5; }
    .badge-listening { background: #1e3a5f; color: #93c5fd; }
    .badge-confirming { background: #4c1d95; color: #c4b5fd; }
    .badge-collecting_issue { background: #1e3a5f; color: #93c5fd; }
    .badge-clarifying { background: #78350f; color: #fcd34d; }
    .badge-vachan_pending { background: #4c1d95; color: #c4b5fd; }
    .badge-vachan_partial { background: #6d28d9; color: #ddd6fe; }
    .badge-resolved { background: #064e3b; color: #6ee7b7; }
    .badge-handover { background: #7c2d12; color: #fb923c; }
    .badge-handover_pending { background: #7c2d12; color: #fb923c; }
    .badge-queued { background: #78350f; color: #fcd34d; }
    .badge-waiting { background: #78350f; color: #fcd34d; }
    .badge-redirected { background: #1e3a5f; color: #93c5fd; }
    .badge-high_help_alert { background: #7f1d1d; color: #fca5a5; }

    /* ── Urgency Bar ── */
    .urgency-bar {
        height: 6px;
        border-radius: 3px;
        background: #1e293b;
        margin-top: 6px;
        overflow: hidden;
    }
    .urgency-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.5s ease;
    }
    .urgency-low { background: linear-gradient(90deg, #22c55e, #4ade80); }
    .urgency-medium { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
    .urgency-high { background: linear-gradient(90deg, #ef4444, #f87171); }
    .urgency-critical { background: linear-gradient(90deg, #dc2626, #ff0000); }

    /* ── Transcript ── */
    .transcript-bubble {
        padding: 8px 14px;
        border-radius: 12px;
        margin: 4px 0;
        max-width: 90%;
        font-size: 0.85rem;
        line-height: 1.4;
    }
    .bubble-caller {
        background: rgba(99, 102, 241, 0.15);
        border: 1px solid rgba(99, 102, 241, 0.3);
        color: #c7d2fe;
        margin-right: auto;
    }
    .bubble-sahayak {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #a7f3d0;
        margin-left: auto;
    }

    /* ── Agent Card ── */
    .agent-card {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.8rem;
    }
    .agent-available { border-left: 4px solid #22c55e; }
    .agent-busy { border-left: 4px solid #ef4444; }

    /* ── Hide Streamlit defaults ── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# API HELPERS
# ──────────────────────────────────────────────

def api_get(endpoint: str) -> dict:
    """GET request to backend API."""
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", timeout=5)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def api_post(endpoint: str, data: dict = None) -> dict:
    """POST request to backend API."""
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", json=data or {}, timeout=5)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ──────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────

def render_header():
    """Render the dashboard header with live stats."""
    active = api_get("/api/active-calls")
    active_count = active.get("count", 0)

    agents_data = api_get("/api/agents")
    agents = agents_data.get("agents", [])
    available_agents = sum(1 for a in agents if a.get("is_available"))

    logs_data = api_get("/api/call-logs")
    total_calls = logs_data.get("count", 0)

    complaints_data = api_get("/api/complaints")
    total_complaints = complaints_data.get("count", 0)

    queue_data = api_get("/api/queue")
    queue_count = queue_data.get("count", 0)

    st.markdown(f"""
    <div class="header-container">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <p class="header-title">🚨 Sahayak 1092 — Command Center</p>
                <p class="header-subtitle">Every Voice Heard. Every Call Resolved. Every Second Counts.</p>
            </div>
            <div style="text-align:right;">
                <p style="color:rgba(255,255,255,0.5); font-size:0.75rem; margin:0;">
                    Last updated: {datetime.now().strftime('%H:%M:%S')}
                </p>
            </div>
        </div>
        <div class="header-stats">
            <div class="stat-box">
                <div class="stat-value" style="color:#f87171;">{active_count}</div>
                <div class="stat-label">Active Calls</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" style="color:#4ade80;">{available_agents}</div>
                <div class="stat-label">Agents Online</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" style="color:#93c5fd;">{total_calls}</div>
                <div class="stat-label">Total Calls</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" style="color:#fbbf24;">{total_complaints}</div>
                <div class="stat-label">Complaints</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" style="color:#fb923c;">{queue_count}</div>
                <div class="stat-label">Queue</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# ACTIVE CALLS PANEL
# ──────────────────────────────────────────────

def render_active_calls():
    """Render live active calls with transcripts and actions."""
    st.subheader("📞 Active Calls")

    data = api_get("/api/active-calls")
    calls = data.get("active_calls", [])

    if not calls:
        st.info("No active calls right now. Sahayak is ready and waiting. 🎯")
        return

    for call in calls:
        sid_short = call.get("call_sid", "?")[-8:]
        language = call.get("language", "unknown").title()
        phase = call.get("phase", "unknown")
        summary = call.get("ai_summary", "Analysing...")
        handover_context = call.get("handover_context") or {}
        selected_agent = handover_context.get("selected_agent") or {}
        routing_breakdown = handover_context.get("routing_score_breakdown") or call.get("routing_score_breakdown") or {}
        officer_first_sentence = (
            handover_context.get("officer_first_sentence")
            or call.get("officer_first_sentence")
            or ""
        )
        similarity_score = call.get("similarity_score")
        similarity_source = call.get("similarity_source") or "local_fallback"
        matched_case_id = call.get("matched_case_id")
        similarity_html = ""
        if similarity_score:
            similarity_html = f"""
            <p style="color:#a7f3d0; margin:4px 0 0; font-size:0.78rem;">
                <strong>Similarity Match:</strong> {int(float(similarity_score) * 100)}%
                <span style="color:rgba(255,255,255,0.4);">• {matched_case_id or 'resolved case'} • {similarity_source}</span>
            </p>
            """
        queue_status = call.get("queue_status") or ""
        queue_position = call.get("queue_position")
        queue_wait = call.get("queue_estimated_wait_sec")
        queue_service = call.get("queue_service_target") or ""
        queue_html = ""
        if queue_status:
            queue_label = queue_status.replace("_", " ").title()
            position_text = f"Position {queue_position}" if queue_position else "Priority queue"
            wait_text = f"Estimated wait {queue_wait}s" if queue_wait is not None else "Wait calculating"
            service_text = f" • Target: {queue_service.title()}" if queue_service else ""
            queue_html = f"""
            <p style="color:#fcd34d; margin:4px 0 0; font-size:0.78rem;">
                <span class="badge badge-{queue_status}">{queue_label}</span>
                <span style="color:rgba(255,255,255,0.55); margin-left:6px;">
                    {position_text} • {wait_text}{service_text}
                </span>
            </p>
            """

        known_phases = (
            "listening",
            "confirming",
            "collecting_issue",
            "clarifying",
            "vachan_pending",
            "vachan_partial",
            "resolved",
            "handover",
            "handover_pending",
            "queued",
        )
        phase_class = f"badge-{phase}" if phase in known_phases else "badge-listening"

        st.markdown(f"""
        <div class="call-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="color:#fff; font-weight:600; font-size:1rem;">
                        📱 {call.get('caller_number', 'Unknown')}
                    </span>
                    <span style="color:rgba(255,255,255,0.4); margin-left:8px; font-size:0.8rem;">
                        SID: {sid_short}
                    </span>
                </div>
                <div>
                    <span class="badge {phase_class}">{phase}</span>
                    <span class="badge badge-calm" style="margin-left:4px;">{language}</span>
                </div>
            </div>
            <p style="color:rgba(255,255,255,0.7); margin:8px 0 4px; font-size:0.85rem;">
                <strong>AI Summary:</strong> {summary}
            </p>
            {similarity_html}
            {queue_html}
        </div>
        """, unsafe_allow_html=True)

        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📞 Take Call", key=f"take_{sid_short}"):
                if phase == "handover_pending" and selected_agent.get("id"):
                    result = api_post(
                        f"/api/handover/{call.get('call_sid')}/accept",
                        {"agent_id": selected_agent["id"]},
                    )
                    if result.get("status") == "ok":
                        st.success(f"Warm handover accepted for {sid_short}")
                        st.json(result.get("transfer", {}), expanded=False)
                    else:
                        st.error(result.get("detail") or result.get("error") or "Handover failed")
                else:
                    st.success(f"Taking over call {sid_short}...")
        with col2:
            if st.button("📋 View Transcript", key=f"transcript_{sid_short}"):
                st.session_state[f"show_transcript_{sid_short}"] = True
        with col3:
            if st.button("✏️ Correct AI", key=f"correct_{sid_short}"):
                st.session_state[f"show_correct_{sid_short}"] = True

        # Transcript viewer
        if handover_context:
            with st.expander("Warm Handover Context", expanded=phase == "handover_pending"):
                st.write(f"**Selected officer:** {selected_agent.get('name', 'Unknown')}")
                st.write(f"**Routing score:** {handover_context.get('routing_score', 0):.3f}")
                st.write(f"**First sentence:** {officer_first_sentence}")
                st.write("**Score breakdown**")
                st.json(routing_breakdown, expanded=False)
                st.write("**Ranked agents**")
                st.json(handover_context.get("ranked_agents", []), expanded=False)

        # Transcript viewer
        if st.session_state.get(f"show_transcript_{sid_short}"):
            with st.expander("Live Transcript", expanded=True):
                # In production, would fetch from API
                st.write("🔄 Transcript streaming...")
                st.caption("Transcript updates in real-time during active calls")

        # Correction panel
        if st.session_state.get(f"show_correct_{sid_short}"):
            with st.expander("Correct AI Analysis", expanded=True):
                new_cat = st.selectbox(
                    "Category",
                    ["theft", "accident", "domestic", "cyber", "noise", "missing_person", "medical", "fire", "general"],
                    key=f"cat_{sid_short}"
                )
                new_urgency = st.slider("Urgency", 0.0, 1.0, 0.5, key=f"urg_{sid_short}")
                if st.button("Apply Corrections", key=f"apply_{sid_short}"):
                    st.success(f"Corrections applied: {new_cat}, urgency {new_urgency:.2f}")

        st.markdown("---")


# ──────────────────────────────────────────────
# CALL HISTORY
# ──────────────────────────────────────────────

def render_call_history():
    """Render call history with filters."""
    st.subheader("📊 Call History")

    data = api_get("/api/call-logs")
    logs = data.get("call_logs", [])

    if not logs:
        st.info("No call history yet. Make a test call to see data here!")
        return

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        outcome_filter = st.selectbox("Outcome", ["All", "ai_resolved", "handed_over", "queued", "ivr_redirect"])
    with col2:
        lang_filter = st.selectbox("Language", ["All", "kannada", "hindi", "english"])
    with col3:
        sort_by = st.selectbox("Sort", ["Newest First", "Highest Urgency"])

    # Filter
    filtered = logs
    if outcome_filter != "All":
        filtered = [log for log in filtered if log.get("outcome") == outcome_filter]
    if lang_filter != "All":
        filtered = [log for log in filtered if log.get("language") == lang_filter]
    if sort_by == "Highest Urgency":
        filtered.sort(key=lambda x: x.get("urgency", 0), reverse=True)

    # Display
    for log in filtered:
        urgency = log.get("urgency", 0) or 0
        urgency_pct = int(urgency * 100)

        if urgency >= 0.9:
            urg_class = "urgency-critical"
        elif urgency >= 0.7:
            urg_class = "urgency-high"
        elif urgency >= 0.4:
            urg_class = "urgency-medium"
        else:
            urg_class = "urgency-low"

        sentiment = log.get("sentiment", "calm") or "calm"
        outcome = log.get("outcome", "in_progress") or "in_progress"
        created = log.get("created_at", "")[:19] if log.get("created_at") else ""
        similarity_score = log.get("similarity_score")
        similarity_source = log.get("similarity_source") or "local_fallback"
        similarity_html = ""
        if similarity_score:
            similarity_html = f"""
            <p style="color:#a7f3d0; margin:4px 0 0; font-size:0.78rem;">
                <strong>Similarity:</strong> {int(float(similarity_score) * 100)}%
                <span style="color:rgba(255,255,255,0.4);">
                    • {log.get('similar_case') or 'resolved case'} • {similarity_source}
                </span>
            </p>
            """

        st.markdown(f"""
        <div class="call-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="color:#fff; font-weight:600;">
                        {log.get('caller_number', 'Unknown')}
                    </span>
                    <span style="color:rgba(255,255,255,0.4); margin-left:8px; font-size:0.75rem;">
                        {created}
                    </span>
                </div>
                <div>
                    <span class="badge badge-{sentiment}">{sentiment}</span>
                    <span class="badge badge-{outcome.replace('_','-') if outcome != 'ai_resolved' else 'resolved'}">
                        {outcome}
                    </span>
                </div>
            </div>
            <p style="color:rgba(255,255,255,0.7); margin:6px 0 2px; font-size:0.85rem;">
                {log.get('ai_summary', 'No summary available')}
            </p>
            {similarity_html}
            <div style="display:flex; align-items:center; gap:8px; margin-top:4px;">
                <span style="color:rgba(255,255,255,0.5); font-size:0.72rem;">
                    Urgency: {urgency_pct}%
                </span>
                <div class="urgency-bar" style="flex:1;">
                    <div class="urgency-fill {urg_class}" style="width:{urgency_pct}%;"></div>
                </div>
                <span style="color:rgba(255,255,255,0.4); font-size:0.72rem;">
                    {log.get('language', '?').title()} • Conf: {int((log.get('confidence', 0) or 0) * 100)}%
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# AGENT MANAGEMENT
# ──────────────────────────────────────────────

def render_agents():
    """Render agent management panel."""
    st.subheader("👮 Agent Management")

    data = api_get("/api/agents")
    agents = data.get("agents", [])

    if not agents:
        st.info("No agents configured. Add agents via Supabase.")
        return

    for agent in agents:
        available = agent.get("is_available", False)
        status_class = "agent-available" if available else "agent-busy"
        status_text = "🟢 Available" if available else "🔴 Busy"
        load = agent.get("current_load", 0) or 0
        languages = ", ".join(agent.get("languages", []))
        specialties = ", ".join(agent.get("specialties", []))

        st.markdown(f"""
        <div class="agent-card {status_class}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="color:#fff; font-weight:600; font-size:1rem;">
                        {agent.get('name', 'Unknown')}
                    </span>
                    <span style="color:rgba(255,255,255,0.4); margin-left:8px; font-size:0.75rem;">
                        {agent.get('badge_id', '')}
                    </span>
                </div>
                <span style="font-size:0.8rem;">{status_text}</span>
            </div>
            <div style="display:flex; gap:1.5rem; margin-top:6px; font-size:0.8rem; color:rgba(255,255,255,0.6);">
                <span>🌐 {languages}</span>
                <span>⚡ {specialties}</span>
                <span>📞 Load: {load}</span>
                <span>⏱️ Avg wait: {agent.get('avg_wait_sec', 0)}s</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Toggle button
        col1, col2 = st.columns([1, 5])
        with col1:
            toggle_label = "Set Busy" if available else "Set Available"
            if st.button(toggle_label, key=f"toggle_{agent.get('id','')}"):
                api_post("/api/agent/toggle", {
                    "agent_id": agent["id"],
                    "available": not available,
                })
                st.rerun()


# ──────────────────────────────────────────────
# KNOWLEDGE BASE
# ──────────────────────────────────────────────

def render_knowledge_base():
    """Render resolved cases knowledge base."""
    st.subheader("📚 Knowledge Base (Resolved Cases)")

    data = api_get("/api/resolved-cases")
    cases = data.get("cases", [])

    if not cases:
        st.info("No resolved cases yet. Cases are auto-added when AI resolves calls.")
        return

    for case in cases:
        tags = case.get("tags", []) or []
        tag_html = " ".join([f'<span class="badge badge-calm">{t}</span>' for t in tags[:4]])

        st.markdown(f"""
        <div class="call-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#fff; font-weight:600; font-size:0.95rem;">
                    {(case.get('category', 'general') or 'general').upper()}
                </span>
                <span style="color:rgba(255,255,255,0.4); font-size:0.72rem;">
                    {(case.get('language', '?') or '?').title()}
                </span>
            </div>
            <p style="color:rgba(255,255,255,0.8); margin:6px 0; font-size:0.85rem;">
                <strong>Issue:</strong> {case.get('summary', '')}
            </p>
            <p style="color:rgba(99,102,241,0.8); margin:4px 0; font-size:0.82rem;">
                <strong>Resolution:</strong> {case.get('resolution', '')}
            </p>
            <div style="margin-top:6px;">{tag_html}</div>
        </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# COMPLAINTS
# ──────────────────────────────────────────────

def render_complaints():
    """Render complaints tracker."""
    st.subheader("📋 Complaints Tracker")

    data = api_get("/api/complaints")
    complaints = data.get("complaints", [])

    if not complaints:
        st.info("No complaints registered yet.")
        return

    for c in complaints:
        status = c.get("status", "registered") or "registered"
        reference_id = c.get("reference_id") or "missing-reference"
        call_sid = c.get("call_sid") or ""
        status_colors = {
            "registered": "#fbbf24",
            "in_progress": "#3b82f6",
            "resolved": "#22c55e",
        }
        color = status_colors.get(status, "#9ca3af")

        st.markdown(f"""
        <div class="call-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="color:#fff; font-weight:600;">
                        {(c.get('category', 'general') or 'general').upper()}
                    </span>
                    <span style="color:rgba(255,255,255,0.45); margin-left:8px; font-size:0.76rem;">
                        {reference_id}
                    </span>
                </div>
                <span style="color:{color}; font-weight:600; font-size:0.82rem;">
                    ● {status.upper()}
                </span>
            </div>
            <p style="color:rgba(255,255,255,0.7); margin:6px 0; font-size:0.85rem;">
                {c.get('description', 'No description')}
            </p>
            <p style="color:rgba(255,255,255,0.4); font-size:0.72rem;">
                {c.get('location', '') or 'Location not captured'} •
                Urgency: {float(c.get('urgency') or 0):.2f} •
                {c.get('language', 'unknown')} •
                Call: {call_sid[-8:] if call_sid else 'n/a'} •
                Created: {(c.get('created_at', '') or '')[:19]}
            </p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"Timeline · {reference_id}", expanded=False):
            timeline_data = api_get(f"/api/complaints/{reference_id}/timeline")
            timeline = timeline_data.get("timeline", [])
            if not timeline:
                st.caption("No timeline events available yet.")
            for event in timeline:
                st.markdown(
                    f"**{event.get('event_type', 'event')}** · "
                    f"{(event.get('created_at', '') or '')[:19]}"
                )
                st.json(event.get("payload", {}), expanded=False)


# ──────────────────────────────────────────────
# PRIORITY QUEUE
# ──────────────────────────────────────────────

def render_queue():
    """Render surge queue and High-Help Alert state."""
    st.subheader("Priority Queue")

    col1, col2 = st.columns([1, 3])
    with col1:
        include_inactive = st.toggle("Show handled entries", value=True)
    endpoint = f"/api/queue?include_inactive={'true' if include_inactive else 'false'}&limit=50"
    data = api_get(endpoint)
    entries = data.get("queue", [])

    if "error" in data:
        st.error(f"Queue unavailable: {data['error']}")
        return

    timeout_sec = data.get("high_help_alert_timeout_sec", 120)
    demo_mode = data.get("demo_mode", False)
    st.caption(
        f"High-Help Alert timeout: {timeout_sec}s"
        + (" in demo mode" if demo_mode else "")
    )

    if not entries:
        st.info("No calls are waiting in the priority queue.")
        return

    high_help_count = sum(1 for item in entries if item.get("status") == "high_help_alert")
    waiting_count = sum(1 for item in entries if item.get("status") == "waiting")
    c1, c2, c3 = st.columns(3)
    c1.metric("Waiting", waiting_count)
    c2.metric("High-Help Alerts", high_help_count)
    c3.metric("Total Shown", len(entries))

    for item in entries:
        status = item.get("status", "waiting") or "waiting"
        status_label = status.replace("_", " ").title()
        sid_short = (item.get("call_sid") or "?")[-8:]
        urgency = float(item.get("urgency") or 0)
        priority = float(item.get("priority_score") or 0)
        wait_sec = item.get("estimated_wait_sec")
        service_target = item.get("service_target") or ""
        created = (item.get("created_at") or "")[:19]
        alert_style = "border-color:rgba(248,113,113,0.8);" if status == "high_help_alert" else ""

        st.markdown(f"""
        <div class="call-card" style="{alert_style}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="color:#fff; font-weight:600;">
                        {item.get('caller_number') or 'Unknown caller'}
                    </span>
                    <span style="color:rgba(255,255,255,0.4); margin-left:8px; font-size:0.75rem;">
                        SID: {sid_short} • {created}
                    </span>
                </div>
                <span class="badge badge-{status}">{status_label}</span>
            </div>
            <p style="color:rgba(255,255,255,0.72); margin:8px 0 4px; font-size:0.85rem;">
                {(item.get('category') or 'general').title()} •
                {(item.get('language') or 'unknown').title()}
                {(' • ' + service_target.title()) if service_target else ''}
            </p>
            <div style="display:flex; gap:1.5rem; color:rgba(255,255,255,0.58); font-size:0.78rem;">
                <span>Position: {item.get('position') or '-'}</span>
                <span>Wait: {wait_sec if wait_sec is not None else '-'}s</span>
                <span>Urgency: {urgency:.0%}</span>
                <span>Priority: {priority:.0%}</span>
                <span>Reason: {item.get('reason') or 'surge'}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# CALL ME (Outbound — Sahayak calls YOU)
# ──────────────────────────────────────────────

def render_call_me():
    """Trigger an outbound call from Sahayak to your phone."""
    st.subheader("📞 Call Me — Sahayak Calls Your Phone")

    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #1e3a5f, #0f2044);
        border: 1px solid rgba(99,102,241,0.3);
        border-radius: 16px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.5rem;
    ">
        <p style="color:#93c5fd; font-size:1rem; font-weight:600; margin:0 0 6px;">🌐 How it works</p>
        <p style="color:rgba(255,255,255,0.7); font-size:0.88rem; margin:0; line-height:1.6;">
            Instead of <em>you</em> dialing the Twilio number (which requires ISD), 
            <strong>Sahayak calls your phone</strong> — from the Twilio number to yours.
            You just need to receive the call. No ISD pack needed.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        phone_input = st.text_input(
            "Your phone number",
            placeholder="e.g. +919876543210  or  9876543210",
            key="callme_phone",
            help="Include country code (+91 for India). If you skip it, +91 is added automatically."
        )
    with col2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        call_btn = st.button("📞 Call Me Now", type="primary", use_container_width=True, key="callme_btn")

    if call_btn:
        phone = phone_input.strip()
        if not phone:
            st.warning("⚠️ Please enter your phone number first.")
        else:
            with st.spinner("☎️ Initiating call — Sahayak is dialling you..."):
                result = api_post("/api/call-me", {"phone": phone})

            if result.get("status") == "calling":
                st.success(f"✅ {result.get('message')}")
                st.markdown(f"""
                <div style="
                    background: rgba(16,185,129,0.1);
                    border: 1px solid rgba(16,185,129,0.3);
                    border-radius: 12px;
                    padding: 1rem 1.5rem;
                    margin-top: 0.5rem;
                ">
                    <p style="color:#6ee7b7; font-weight:600; margin:0 0 4px;">📋 Call Details</p>
                    <p style="color:rgba(255,255,255,0.7); font-size:0.85rem; margin:2px 0;">
                        <strong>From:</strong> {result.get('from', 'Twilio number')}
                    </p>
                    <p style="color:rgba(255,255,255,0.7); font-size:0.85rem; margin:2px 0;">
                        <strong>To:</strong> {result.get('to', phone)}
                    </p>
                    <p style="color:rgba(255,255,255,0.7); font-size:0.85rem; margin:2px 0;">
                        <strong>Call SID:</strong> <code>{result.get('call_sid', 'N/A')}</code>
                    </p>
                    <p style="color:rgba(255,255,255,0.5); font-size:0.78rem; margin-top:8px;">
                        📱 Pick up the call — Sahayak will greet you and start the demo.
                    </p>
                </div>
                """, unsafe_allow_html=True)
            elif "error" in result:
                st.error(f"❌ Call failed: {result.get('error') or result.get('detail', 'Unknown error')}")
                if "Twilio credentials" in str(result.get('error', '') + result.get('detail', '')):
                    st.info("💡 Make sure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are set in your .env file.")
            else:
                st.error(f"❌ Unexpected response: {result}")

    st.markdown("---")
    st.markdown("**💡 Troubleshooting tips:**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        - ✅ Include country code: `+91` for India  
        - ✅ Your number must be **Twilio-verified** (trial accounts)  
        - ✅ ngrok must be running & `BASE_URL` set in `.env`
        """)
    with col2:
        st.markdown("""
        - ✅ Backend must be running on port 8000  
        - ✅ Twilio credentials must be in `.env`  
        - ✅ Twilio account must have call credits  
        """)

    # Quick health check
    with st.expander("🔍 Check backend health"):
        health = api_get("/health")
        if "error" not in health:
            st.success(f"✅ Backend is healthy — {health.get('service')} v{health.get('version')}")
            st.json(health)
        else:
            st.error(f"❌ Backend unreachable: {health.get('error')}")
            st.info("Start the backend with: `py -m backend.main`")


# ──────────────────────────────────────────────
# TEST PIPELINE (Demo Tool)
# ──────────────────────────────────────────────

def render_test_pipeline():
    """Interactive test tool to try the AI pipeline without a phone."""
    st.subheader("🧪 Test Pipeline (No Phone Needed)")

    if "test_call_sid" not in st.session_state:
        st.session_state.test_call_sid = f"test-{int(time.time())}"

    col1, col2 = st.columns([3, 1])
    with col1:
        test_input = st.text_input(
            "Simulate caller input",
            placeholder="e.g., ನನ್ನ ಮೊಬೈಲ್ ಕಳೆದುಹೋಗಿದೆ (My phone was stolen)",
            key="test_input",
        )
    with col2:
        test_lang = st.selectbox("Language", ["kannada", "hindi", "english"], key="test_lang")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎯 Send to Sahayak", type="primary", use_container_width=True):
            if test_input:
                with st.spinner("Processing..."):
                    result = api_post("/api/test-pipeline", {
                        "text": test_input,
                        "call_sid": st.session_state.test_call_sid,
                        "language": test_lang,
                    })

                if "error" not in result:
                    st.markdown("---")
                    st.markdown("**🤖 Sahayak says:**")
                    st.success(result.get("response", "No response"))
                    st.markdown(f"**Action:** `{result.get('action', '?')}`")

                    cs = result.get("call_state", {})
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Phase", cs.get("phase", "?"))
                    c2.metric("Urgency", f"{cs.get('urgency', 0):.0%}")
                    c3.metric("Confidence", f"{cs.get('confidence', 0):.0%}")
                    c4.metric("Sentiment", cs.get("sentiment", "?"))
                    if cs.get("queue_status"):
                        st.warning(
                            "Queue: "
                            f"{cs.get('queue_status')} • "
                            f"position {cs.get('queue_position') or '-'} • "
                            f"wait {cs.get('queue_estimated_wait_sec') if cs.get('queue_estimated_wait_sec') is not None else '-'}s"
                        )
                    similarity = result.get("similarity") or {}
                    if similarity:
                        st.info(
                            "Matched resolved case "
                            f"`{similarity.get('matched_case_id')}` at "
                            f"{float(similarity.get('similarity_score', 0)):.0%} similarity "
                            f"via `{similarity.get('retrieval_source', 'local_fallback')}`."
                        )
                        st.caption(similarity.get("adapted_resolution", ""))
                else:
                    st.error(f"Error: {result['error']}")
            else:
                st.warning("Please enter some text to test")

    with col2:
        if st.button("🔄 New Test Call", use_container_width=True):
            st.session_state.test_call_sid = f"test-{int(time.time())}"
            st.rerun()

    st.caption(f"Test Call SID: `{st.session_state.test_call_sid}`")


# ──────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ──────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:1rem 0;">
        <span style="font-size:2.5rem;">🚨</span>
        <h2 style="margin:0.3rem 0 0; color:#fff; font-size:1.3rem;">Sahayak 1092</h2>
        <p style="color:rgba(255,255,255,0.5); font-size:0.75rem; margin:0;">AI Command Center v1.0</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    page = st.radio(
        "Navigation",
        [
            "📞 Call Me",
            "📞 Active Calls",
            "🚦 Queue",
            "📊 Call History",
            "👮 Agents",
            "📚 Knowledge Base",
            "📋 Complaints",
            "🧪 Test Pipeline",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Auto-refresh toggle
    auto_refresh = st.toggle("🔄 Auto Refresh (5s)", value=False)

    if st.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()

    st.markdown("---")
    st.caption("Built for AI for Bharat 2026")
    st.caption("Theme 12: AI for 1092 Helpline")


# ──────────────────────────────────────────────
# MAIN RENDER
# ──────────────────────────────────────────────

render_header()

if page == "📞 Call Me":
    render_call_me()
elif page == "📞 Active Calls":
    render_active_calls()
elif page == "🚦 Queue":
    render_queue()
elif page == "📊 Call History":
    render_call_history()
elif page == "👮 Agents":
    render_agents()
elif page == "📚 Knowledge Base":
    render_knowledge_base()
elif page == "📋 Complaints":
    render_complaints()
elif page == "🧪 Test Pipeline":
    render_test_pipeline()

# Auto-refresh
if auto_refresh:
    time.sleep(5)
    st.rerun()
