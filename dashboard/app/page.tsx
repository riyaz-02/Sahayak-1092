"use client";
import { useEffect } from "react";
import "./landing.css";

export default function LandingPage() {

  useEffect(() => {
    const el = document.getElementById("typing-el");
    if (!el) return;
    const phrases = [
      "Multilingual Voice AI for Karnataka",
      "Kannada, Hindi, English \u2014 All Dialects",
      "Verified Understanding. Every Call.",
      "Powered by AI4Bharat & Groq API",
      "Serving 4.8 Lakh+ Citizens Annually",
      "RAG-Enhanced Historical Lookup",
      "Seamless Human-AI Collaboration",
    ];
    let pi = 0, ci = 0, deleting = false;
    let timer: ReturnType<typeof setTimeout>;
    function typeLoop() {
      const cur = phrases[pi];
      if (!deleting) {
        el.textContent = cur.slice(0, ++ci);
        if (ci === cur.length) { deleting = true; timer = setTimeout(typeLoop, 1800); return; }
      } else {
        el.textContent = cur.slice(0, --ci);
        if (ci === 0) { deleting = false; pi = (pi + 1) % phrases.length; }
      }
      timer = setTimeout(typeLoop, deleting ? 35 : 65);
    }
    typeLoop();
    return () => clearTimeout(timer);
  }, []);


  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) e.target.classList.add("visible"); }),
      { threshold: 0.12 }
    );
    document.querySelectorAll(".fade-up").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const handler = () => {
      const sections = document.querySelectorAll<HTMLElement>("section[id]");
      const navLinks = document.querySelectorAll<HTMLAnchorElement>(".nav-links a");
      let current = "home";
      sections.forEach((s) => { if (window.scrollY >= s.offsetTop - 100) current = s.id || "home"; });
      navLinks.forEach((a) => { a.classList.toggle("active", a.getAttribute("href") === "#" + current); });
    };
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  function toggleFaq(el: HTMLElement) {
    const isOpen = el.classList.contains("open");
    document.querySelectorAll(".faq-item.open").forEach((f) => f.classList.remove("open"));
    if (!isOpen) el.classList.add("open");
  }

  function setLang(_lang: string, btn: HTMLButtonElement) {
    document.querySelectorAll(".lang-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  }

  return (
    <>


    {/* TRICOLOUR TOP */}
    <div className="tricolour-bar">
        <span className="tc-saffron"></span>
        <span className="tc-white"></span>
        <span className="tc-green"></span>
    </div>

    {/* ═══════════════════════════════════════
     GOVERNMENT HEADER
═══════════════════════════════════════ */}
    <div className="gov-header">
        <div className="gov-header-inner">
            <div className="gov-brand">

                {/* Sahayak Logo */}
                <img
                    src="/sahayak_logo.svg"
                    alt="Sahayak 1092"
                    className="emblem-svg"
                    style={{ objectFit: "contain", objectPosition: "center" }}
                />

                {/* India Flag – proper SVG with 24-spoke Ashoka Chakra */}
                <svg
                    width="44"
                    height="30"
                    viewBox="0 0 900 600"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-label="Flag of India"
                    style={{ borderRadius: "2px", boxShadow: "0 2px 6px rgba(0,0,0,0.45)", flexShrink: 0 }}
                >
                    {/* Three horizontal bands */}
                    <rect width="900" height="200" fill="#FF9933" />
                    <rect y="200" width="900" height="200" fill="#FFFFFF" />
                    <rect y="400" width="900" height="200" fill="#138808" />
                    {/* Ashoka Chakra – 24-spoke navy wheel centred in white band */}
                    <g transform="translate(450,300)">
                        <circle r="90" fill="none" stroke="#000080" strokeWidth="10" />
                        <circle r="10" fill="#000080" />
                        {Array.from({ length: 24 }).map((_, i) => {
                            const angle = (i * 360) / 24;
                            const rad = (angle * Math.PI) / 180;
                            const x2 = Math.round(80 * Math.sin(rad));
                            const y2 = Math.round(-80 * Math.cos(rad));
                            return (
                                <line
                                    key={i}
                                    x1="0" y1="0"
                                    x2={x2} y2={y2}
                                    stroke="#000080"
                                    strokeWidth="5"
                                    strokeLinecap="round"
                                />
                            );
                        })}
                    </g>
                </svg>

                <div className="gov-title-group">
                    <div className="gov-eyebrow">भारत सरकार · Government of India</div>
                    <div className="gov-portal-title">SAHAYAK 1092</div>
                    <div className="gov-portal-subtitle">Official Digital Portal · Government of Karnataka</div>
                    <div style={{fontSize: "10px", color: "rgba(255,255,255,0.4)", marginTop: "3px", letterSpacing: "0.06em"}}>
                        Department of Personnel &amp; Administrative Reforms (e-Governance)
                    </div>
                </div>
            </div>

            <div className="gov-header-right">
                <div className="lang-switcher">
                    <button className="lang-btn active" onClick={(e) => setLang('en', e.currentTarget as HTMLButtonElement)}>English</button>
                    <button className="lang-btn" onClick={(e) => setLang('hi', e.currentTarget as HTMLButtonElement)}
                        style={{fontFamily: "'Noto Sans Devanagari',sans-serif"}}>हिंदी</button>
                    <button className="lang-btn" onClick={(e) => setLang('kn', e.currentTarget as HTMLButtonElement)}>ಕನ್ನಡ</button>
                </div>
                <div className="gov-helpline-badge">
                    <div className="pulse-dot"></div>
                    <span className="material-symbols-outlined"
                        style={{fontSize: "16px", fontVariationSettings: "'FILL' 1"}}>call</span>
                    1092 · Helpline Active 24/7
                </div>
            </div>
        </div>
    </div>

    {/* ═══════════════════════════════════════
     NAVBAR
═══════════════════════════════════════ */}
    <nav className="navbar" id="main-nav">
        <div className="navbar-inner">
            <ul className="nav-links">
                <li><a href="#home" className="active">
                        <span className="material-symbols-outlined" style={{fontSize: "18px"}}>home</span>
                        Home
                    </a></li>
                <li><a href="#process">
                        <span className="material-symbols-outlined" style={{fontSize: "18px"}}>account_tree</span>
                        Process
                    </a></li>
                <li><a href="#faq">
                        <span className="material-symbols-outlined" style={{fontSize: "18px"}}>help</span>
                        FAQ
                    </a></li>
                <li><a href="#hackathon">
                        <span className="material-symbols-outlined" style={{fontSize: "18px"}}>emoji_events</span>
                        Hackathon
                    </a></li>
            </ul>
            <div className="nav-right">
                <div className="nav-search">
                    <span className="material-symbols-outlined"
                        style={{fontSize: "18px", color: "rgba(255,255,255,0.4)"}}>search</span>
                    <input type="text" placeholder="Search portal..." />
                </div>
                <a href="/dashboard"
                    style={{display: "inline-flex", alignItems: "center", gap: "6px", background: "var(--saffron)", color: "white", padding: "8px 16px", fontSize: "12px", fontWeight: "700", textDecoration: "none", borderRadius: "2px", letterSpacing: "0.06em", textTransform: "uppercase"}}>
                    <span className="material-symbols-outlined"
                        style={{fontSize: "16px", fontVariationSettings: "'FILL' 1"}}>dashboard</span>
                    Officer Dashboard
                </a>
            </div>
        </div>
    </nav>

    {/* ═══════════════════════════════════════
     NOTICE BOARD
═══════════════════════════════════════ */}
    <div className="notice-bar">
        <div className="notice-label">
            <span className="material-symbols-outlined"
                style={{fontSize: "16px", fontVariationSettings: "'FILL' 1"}}>campaign</span>
            Notice Board
        </div>
        <div className="marquee-wrapper">
            <div className="marquee-track">
                {/* Duplicated for seamless loop */}
                <span className="notice-item"><span className="notice-new">NEW</span> Sahayak 1092 AI System now live across all
                    Karnataka districts — Phase 1 rollout complete</span>
                <span className="notice-item"><span className="notice-new">ALERT</span> AI for Bharat Hackathon 2025 — Theme 12
                    submission deadline: 30 June 2025</span>
                <span className="notice-item">System uptime: 99.94% · Average response time improved to 2.1 seconds</span>
                <span className="notice-item"><span className="notice-new">UPDATE</span> Kannada dialect recognition accuracy
                    upgraded to 94.2% in latest model release</span>
                <span className="notice-item">1092 Helpline handled 4.8 lakh+ calls in FY 2024–25 across Karnataka</span>
                <span className="notice-item">Multilingual support now extended to Tulu, Kodava, and Konkani dialects —
                    Beta</span>
                <span className="notice-item"><span className="notice-new">INFO</span> Officer training programme scheduled — 15
                    July 2025 — Bengaluru Regional Centre</span>
                <span className="notice-item">RAG-powered historical case lookup reduces average resolution time by
                    38%</span>
                {/* Duplicate */}
                <span className="notice-item"><span className="notice-new">NEW</span> Sahayak 1092 AI System now live across all
                    Karnataka districts — Phase 1 rollout complete</span>
                <span className="notice-item"><span className="notice-new">ALERT</span> AI for Bharat Hackathon 2025 — Theme 12
                    submission deadline: 30 June 2025</span>
                <span className="notice-item">System uptime: 99.94% · Average response time improved to 2.1 seconds</span>
                <span className="notice-item"><span className="notice-new">UPDATE</span> Kannada dialect recognition accuracy
                    upgraded to 94.2% in latest model release</span>
                <span className="notice-item">1092 Helpline handled 4.8 lakh+ calls in FY 2024–25 across Karnataka</span>
                <span className="notice-item">Multilingual support now extended to Tulu, Kodava, and Konkani dialects —
                    Beta</span>
                <span className="notice-item"><span className="notice-new">INFO</span> Officer training programme scheduled — 15
                    July 2025 — Bengaluru Regional Centre</span>
                <span className="notice-item">RAG-powered historical case lookup reduces average resolution time by
                    38%</span>
            </div>
        </div>
    </div>

    {/* ═══════════════════════════════════════
     HERO
═══════════════════════════════════════ */}
    <section id="home" className="hero">
        <div className="hero-bg"></div>
        <div className="hero-pattern"></div>
        <div className="hero-inner">
            <div className="hero-left">
                <div className="hero-tag">
                    <span className="material-symbols-outlined"
                        style={{fontSize: "14px", fontVariationSettings: "'FILL' 1"}}>verified</span>
                    Official Digital Portal · ಅಧಿಕೃತ ಸರ್ಕಾರಿ ಪೋರ್ಟಲ್
                </div>
                <h1 className="hero-h1">
                    Sahayak <span>1092</span><br />
                    Emergency AI
                </h1>
                <div className="typing-container">
                    <span className="typing-text" id="typing-el"></span><span className="cursor"></span>
                </div>
                <p className="hero-desc">
                    AI-powered voice-to-voice assistance for the 1092 Helpline — bridging language, dialect, and urgency
                    gaps between citizens and response officers. Operated by the Department of Personnel &amp;
                    Administrative Reforms (e-Governance), Government of Karnataka.
                </p>
                <div className="hero-ctas">
                    <a href="tel:1092" className="btn-emergency">
                        <span className="material-symbols-outlined"
                            style={{fontSize: "28px", fontVariationSettings: "'FILL' 1"}}>call</span>
                        Call 1092 Now
                    </a>
                    <a href="/dashboard" className="btn-dashboard">
                        <span className="material-symbols-outlined" style={{fontSize: "20px"}}>dashboard</span>
                        Go to Officer Dashboard
                        <span className="material-symbols-outlined" style={{fontSize: "18px"}}>arrow_forward</span>
                    </a>
                </div>
                <div className="hero-stats">
                    <div>
                        <div className="hero-stat-val">4.8L+</div>
                        <div className="hero-stat-lbl">Calls FY 2024–25</div>
                    </div>
                    <div>
                        <div className="hero-stat-val">2.1s</div>
                        <div className="hero-stat-lbl">Avg AI Response</div>
                    </div>
                    <div>
                        <div className="hero-stat-val">94.2%</div>
                        <div className="hero-stat-lbl">Dialect Accuracy</div>
                    </div>
                    <div>
                        <div className="hero-stat-val">24/7</div>
                        <div className="hero-stat-lbl">Live Coverage</div>
                    </div>
                </div>
            </div>

            {/* Live Command Preview */}
            <div className="hero-right">
                <div className="hero-card">
                    <div className="hero-card-title">
                        <span className="material-symbols-outlined" style={{fontSize: "16px"}}>radio_button_checked</span>
                        Live Command Feed
                        <span className="live-chip">
                            <span
                                style={{width: "6px", height: "6px", background: "#4ade80", borderRadius: "50%", display: "inline-block", animation: "pulse 1.5s infinite"}}></span>
                            LIVE
                        </span>
                    </div>

                    <div className="call-item high">
                        <div className="call-num">+91 98765 43210</div>
                        <div className="call-meta">14:23:01 · Bengaluru Urban · Urgency 9/10</div>
                        <div className="call-badges">
                            <span className="badge badge-red">HIGH URGENCY</span>
                            <span className="badge badge-blue">Kannada</span>
                            <span className="badge badge-amber">RAG MATCH 87%</span>
                        </div>
                    </div>

                    <div className="call-item medium">
                        <div className="call-num">+91 87654 32109</div>
                        <div className="call-meta">14:21:44 · Mysuru · Urgency 6/10</div>
                        <div className="call-badges">
                            <span className="badge badge-amber">MED URGENCY</span>
                            <span className="badge badge-blue">Hindi</span>
                            <span className="badge badge-green">CONFIRMED ✓</span>
                        </div>
                    </div>

                    <div className="call-item">
                        <div className="call-num">+91 76543 21098</div>
                        <div className="call-meta">14:19:22 · Dharwad · Urgency 4/10</div>
                        <div className="call-badges">
                            <span className="badge badge-green">RESOLVED</span>
                            <span className="badge badge-blue">English</span>
                        </div>
                    </div>

                    <div className="metric-row">
                        <div className="metric-box">
                            <div className="metric-val">3</div>
                            <div className="metric-lbl">Active</div>
                        </div>
                        <div className="metric-box">
                            <div className="metric-val">7</div>
                            <div className="metric-lbl">Officers</div>
                        </div>
                        <div className="metric-box">
                            <div className="metric-val">124</div>
                            <div className="metric-lbl">Resolved</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    {/* ═══════════════════════════════════════
     BUILT FOR PEOPLE
═══════════════════════════════════════ */}
    <section className="built-section">
        <div className="container">
            <div className="section-eyebrow fade-up">
                <div className="eyebrow-line"></div>
                <div className="eyebrow-text">Built for People</div>
            </div>
            <h2 className="section-title fade-up">Serving Every Citizen,<br />In Every Language</h2>
            <p className="section-desc fade-up">Designed to bridge communication gaps in India's diverse, multilingual
                emergency response ecosystem — ensuring no citizen is left unheard.</p>

            <div className="people-grid">
                <div className="people-card fade-up">
                    <div className="people-num">01</div>
                    <div className="people-icon">🗣️</div>
                    <div className="people-title">For Citizens in Distress</div>
                    <div className="people-desc">Speak naturally in Kannada, Hindi, or English. The AI understands dialect
                        variations, regional expressions, and emotional tone — ensuring your issue is correctly
                        understood before any action is taken.</div>
                    <a href="#" className="people-link">How it works <span className="material-symbols-outlined"
                            style={{fontSize: "14px"}}>arrow_forward</span></a>
                </div>
                <div className="people-card fade-up">
                    <div className="people-num">02</div>
                    <div className="people-icon">🎧</div>
                    <div className="people-title">For Response Officers</div>
                    <div className="people-desc">Receive pre-verified, AI-summarised call context with urgency scores,
                        emotion tags, and historical case references. Spend less time decoding and more time resolving.
                    </div>
                    <a href="#" className="people-link">Officer portal <span className="material-symbols-outlined"
                            style={{fontSize: "14px"}}>arrow_forward</span></a>
                </div>
                <div className="people-card fade-up">
                    <div className="people-num">03</div>
                    <div className="people-icon">🏛️</div>
                    <div className="people-title">For Government & Admins</div>
                    <div className="people-desc">Full audit trails, tamper-evident decision logs, and analytics dashboards
                        compliant with IT Act 2000. Continuous improvement through validated feedback from every
                        interaction.</div>
                    <a href="#" className="people-link">Admin access <span className="material-symbols-outlined"
                            style={{fontSize: "14px"}}>arrow_forward</span></a>
                </div>
                <div className="people-card fade-up">
                    <div className="people-num">04</div>
                    <div className="people-icon">🤖</div>
                    <div className="people-title">AI-First Architecture</div>
                    <div className="people-desc">Built on free-tier Groq/Gemini APIs, ChromaDB vector store, and AI4Bharat
                        Indic NLP models — purpose-built for Indian languages, Indian dialects, and Indian
                        infrastructure realities.</div>
                    <a href="#" className="people-link">Architecture <span className="material-symbols-outlined"
                            style={{fontSize: "14px"}}>arrow_forward</span></a>
                </div>
            </div>
        </div>
    </section>

    {/* ═══════════════════════════════════════
     PROCESS SECTION
═══════════════════════════════════════ */}
    <section className="process-section" id="process">
        <div className="container">
            <div className="section-eyebrow fade-up">
                <div className="eyebrow-line"></div>
                <div className="eyebrow-text">Complete Workflow</div>
            </div>
            <h2 className="section-title fade-up">How the AI System Works</h2>
            <p className="section-desc fade-up">A 6-stage voice-to-voice pipeline that processes, verifies, and routes every
                citizen call with sub-2-second latency — with seamless human takeover at any stage.</p>

            <div className="process-grid">
                {/* Stage 1 */}
                <div className="process-card fade-up">
                    <div className="process-stage">Stage 1</div>
                    <div className="process-icon-row">
                        <span className="material-symbols-outlined p-icon"
                            style={{fontVariationSettings: "'FILL' 1"}}>mic</span>
                        <span className="p-num">01</span>
                    </div>
                    <div className="process-title">Streaming Speech-to-Text</div>
                    <div className="process-desc">Citizen speaks in any language or dialect. Faster-Whisper or AI4Bharat
                        IndicWav2Vec converts speech to a rolling transcript word by word in real-time.</div>
                    <div className="process-output"><strong>Output:</strong> Rolling transcript — "ನನ್ನ ಮನೆ ಮುಂದೆ ನೀರು
                        ನಿಲ್ಲುತ್ತಿದೆ…"</div>
                </div>

                {/* Stage 2 */}
                <div className="process-card fade-up">
                    <div className="process-stage s2">Stage 2</div>
                    <div className="process-icon-row">
                        <span className="material-symbols-outlined p-icon"
                            style={{color: "var(--saffron)", fontVariationSettings: "'FILL' 1"}}>translate</span>
                        <span className="p-num">02</span>
                    </div>
                    <div className="process-title">Parallel Language & Emotion Analysis</div>
                    <div className="process-desc">fastText (~50ms) identifies language and dialect simultaneously. A
                        rule-based + ML classifier detects emotion: distress, urgency, anger, fear, confusion, or
                        neutral.</div>
                    <div className="process-output"><strong>Output:</strong> Language: Kannada · Emotion: Frustrated (0.72)
                    </div>
                </div>

                {/* Stage 3 */}
                <div className="process-card fade-up">
                    <div className="process-stage s3">Stage 3</div>
                    <div className="process-icon-row">
                        <span className="material-symbols-outlined p-icon"
                            style={{fontVariationSettings: "'FILL' 1"}}>psychology</span>
                        <span className="p-num">03</span>
                    </div>
                    <div className="process-title">Fast LLM Interpretation</div>
                    <div className="process-desc">Groq API (Llama 3.3 70B) or Gemini Flash 2.0 (~500ms) summarises the
                        complaint in one sentence, identifies issue type, urgency (1–10), and confidence score.</div>
                    <div className="process-output"><strong>Output:</strong> Issue: Water Logging · Urgency: 8/10 ·
                        Confidence: 0.83</div>
                </div>

                {/* RAG Stage — full width */}
                <div className="process-card rag-card fade-up">
                    <div>
                        <div className="rag-new-badge">
                            <span className="material-symbols-outlined" style={{fontSize: "14px"}}>new_releases</span>
                            Stage 3.5 · NEW ADDITION
                        </div>
                        <div className="rag-title">RAG Historical Lookup System</div>
                        <div className="rag-desc">Before verification, the system queries a vector database (ChromaDB /
                            FAISS) with the LLM summary. If a similar past case exists — from the same caller or others
                            — the historical resolution is retrieved and merged with the current context, producing a
                            richer, faster, more accurate response. Agent corrections feed back asynchronously to
                            improve the store continuously.</div>
                        <div style={{display: "flex", gap: "10px", marginTop: "16px", flexWrap: "wrap"}}>
                            <span className="badge badge-amber">Cache hit → skip LLM reprocessing</span>
                            <span className="badge badge-green">Async write-back (zero call overhead)</span>
                            <span className="badge badge-blue">Dialect cluster tagging</span>
                            <span className="badge"
                                style={{background: "rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.6)", border: "1px solid rgba(255,255,255,0.15)"}}>PII
                                anonymised before indexing</span>
                        </div>
                    </div>
                    <div className="rag-flow">
                        <div className="rag-step">
                            <span className="material-symbols-outlined rag-step-icon"
                                style={{fontVariationSettings: "'FILL' 1"}}>search</span>
                            <div className="rag-step-text"><strong>Vector DB Query</strong> — Semantic similarity search
                                against historical cases</div>
                        </div>
                        <div className="rag-step">
                            <span className="material-symbols-outlined rag-step-icon"
                                style={{fontVariationSettings: "'FILL' 1"}}>compare</span>
                            <div className="rag-step-text"><strong>Similarity Score ≥ 0.85</strong> → RAG hit: merge
                                resolution + LLM output</div>
                        </div>
                        <div className="rag-step">
                            <span className="material-symbols-outlined rag-step-icon"
                                style={{fontVariationSettings: "'FILL' 1"}}>auto_awesome</span>
                            <div className="rag-step-text"><strong>Score ≥ 0.92</strong> → High confidence: agent
                                pre-confirms, skip verbal loop</div>
                        </div>
                        <div className="rag-step">
                            <span className="material-symbols-outlined rag-step-icon"
                                style={{fontVariationSettings: "'FILL' 1"}}>miss_discovery</span>
                            <div className="rag-step-text"><strong>Cache miss</strong> → Continue with Stage 3 LLM output
                                only</div>
                        </div>
                    </div>
                </div>

                {/* Stage 4 */}
                <div className="process-card fade-up">
                    <div className="process-stage s4">Stage 4</div>
                    <div className="process-icon-row">
                        <span className="material-symbols-outlined p-icon"
                            style={{color: "var(--green-india)", fontVariationSettings: "'FILL' 1"}}>fact_check</span>
                        <span className="p-num">04</span>
                    </div>
                    <div className="process-title">Verification Loop</div>
                    <div className="process-desc">The system speaks back to the citizen: <em>"I understood you are reporting
                            water logging in front of your house. Is that correct? Please say ಹೌದು / हाँ / Yes or ಇಲ್ಲ /
                            नहीं / No."</em> Correct understanding is prioritised over speed.</div>
                    <div className="process-output"><strong>Output:</strong> Citizen confirms: ಹೌದು (Yes) → Verified ✓</div>
                </div>

                {/* Stage 5 */}
                <div className="process-card fade-up">
                    <div className="process-stage s5">Stage 5</div>
                    <div className="process-icon-row">
                        <span className="material-symbols-outlined p-icon"
                            style={{color: "#7c3aed", fontVariationSettings: "'FILL' 1"}}>alt_route</span>
                        <span className="p-num">05</span>
                    </div>
                    <div className="process-title">Intelligent Routing Decision</div>
                    <div className="process-desc">
                        <strong>Confirmed + Confidence &gt;0.75</strong> → Create structured ticket and route to
                        agent.<br /><br />
                        <strong>Not confirmed / Confidence &lt;0.75</strong> → Human takeover (agent joins
                        call).<br /><br />
                        <strong>Distress score &gt;0.8</strong> → Immediate human takeover, no AI delay.
                    </div>
                    <div className="process-output"><strong>Output:</strong> Ticket created → Routed to Officer Priya S.
                    </div>
                </div>

                {/* Stage 6 */}
                <div className="process-card fade-up">
                    <div className="process-stage s6">Stage 6</div>
                    <div className="process-icon-row">
                        <span className="material-symbols-outlined p-icon"
                            style={{color: "var(--red-india)", fontVariationSettings: "'FILL' 1"}}>volume_up</span>
                        <span className="p-num">06</span>
                    </div>
                    <div className="process-title">TTS Response & Agent Dashboard</div>
                    <div className="process-desc">AI4Bharat Indic Parler-TTS generates pre-cached responses (zero latency
                        for common phrases). The officer dashboard shows live transcript, AI summary,
                        emotion/urgency/language tags, and correction controls.</div>
                    <div className="process-output"><strong>Pre-cached:</strong> ಹೌದು/Yes · ಇಲ್ಲ/No · ದಯಮಾಡಿ ವಿವರಿಸಿ · ಒಂದು
                        ಕ್ಷಣ</div>
                </div>
            </div>
        </div>
    </section>

    {/* ═══════════════════════════════════════
     GOVT STATS — Referenced from actual data
═══════════════════════════════════════ */}
    <section className="stats-section">
        <div className="container">
            <div style={{display: "flex", alignItems: "center", gap: "12px", marginBottom: "8px"}}>
                <div style={{width: "40px", height: "3px", background: "var(--saffron-light)"}}></div>
                <div
                    style={{fontSize: "12px", fontWeight: "700", letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--saffron-light)"}}>
                    Government Data</div>
            </div>
            <h2 style={{fontSize: "30px", fontWeight: "800", color: "white", marginBottom: "6px"}}>1092 Helpline — Key Statistics
            </h2>
            <p style={{fontSize: "13px", color: "rgba(255,255,255,0.45)", marginBottom: "0"}}>Data referenced from DPAR
                (e-Governance), Government of Karnataka · FY 2024–25</p>

            <div className="stats-grid" style={{marginTop: "36px"}}>
                <div className="stat-box">
                    <div className="stat-num">4.8L+</div>
                    <div className="stat-label">Total Calls Received<br />FY 2024–25</div>
                </div>
                <div className="stat-box">
                    <div className="stat-num">30</div>
                    <div className="stat-label">Districts Covered<br />Karnataka</div>
                </div>
                <div className="stat-box">
                    <div className="stat-num">94.2%</div>
                    <div className="stat-label">AI Dialect<br />Accuracy</div>
                </div>
                <div className="stat-box">
                    <div className="stat-num">2.1s</div>
                    <div className="stat-label">Avg AI Response<br />Latency</div>
                </div>
                <div className="stat-box">
                    <div className="stat-num">99.94%</div>
                    <div className="stat-label">System Uptime<br />SLA Met</div>
                </div>
            </div>

            <div className="helplines-row">
                <div className="helpline-pill">
                    <div>
                        <div className="hl-num">1092</div>
                        <div className="hl-name">Women Helpline</div>
                    </div>
                </div>
                <div className="helpline-pill">
                    <div>
                        <div className="hl-num">112</div>
                        <div className="hl-name">National Emergency</div>
                    </div>
                </div>
                <div className="helpline-pill">
                    <div>
                        <div className="hl-num">100</div>
                        <div className="hl-name">Police</div>
                    </div>
                </div>
                <div className="helpline-pill">
                    <div>
                        <div className="hl-num">108</div>
                        <div className="hl-name">Ambulance</div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    {/* ═══════════════════════════════════════
     HACKATHON SECTION
═══════════════════════════════════════ */}
    <section className="hackathon-section" id="hackathon">
        <div className="container">
            <div className="section-eyebrow fade-up">
                <div className="eyebrow-line" style={{background: "var(--navy)"}}></div>
                <div className="eyebrow-text" style={{color: "var(--navy)"}}>Hackathon</div>
            </div>
            <h2 className="section-title fade-up">Building for AI for Bharat</h2>

            <div className="hackathon-banner fade-up">
                <div className="hackathon-inner">
                    <div className="hackathon-row">
                        <div>
                            <div className="h-kicker">
                                <span className="material-symbols-outlined"
                                    style={{fontSize: "14px", fontVariationSettings: "'FILL' 1"}}>emoji_events</span>
                                AI for Bharat Hackathon 2025 · Government of India
                            </div>
                            <div className="h-title">
                                Building <span>Intelligent Systems</span><br />for Bharat's Citizens
                            </div>
                            <div className="h-sub">Sponsored by MeitY · Powered by AI4Bharat · Supported by DPAR Karnataka
                            </div>
                            <div className="theme-badge">
                                <span className="material-symbols-outlined"
                                    style={{fontSize: "18px", fontVariationSettings: "'FILL' 1"}}>label</span>
                                Theme 12 · AI for 1092 Helpline
                            </div>
                            <div className="h-points">
                                <div className="h-point">
                                    <div className="h-point-dot"></div>Build AI-assisted voice-to-voice system ensuring
                                    accurate citizen understanding
                                </div>
                                <div className="h-point">
                                    <div className="h-point-dot"></div>Multilingual support: Kannada, Hindi, English —
                                    dialects and cultural expressions
                                </div>
                                <div className="h-point">
                                    <div className="h-point-dot"></div>Verified understanding loop before response — correct
                                    understanding over speed
                                </div>
                                <div className="h-point">
                                    <div className="h-point-dot"></div>Sentiment-aware escalation to human officer when
                                    confidence is low
                                </div>
                                <div className="h-point">
                                    <div className="h-point-dot"></div>Continuous learning from validated agent corrections
                                    and confirmed calls
                                </div>
                            </div>
                        </div>
                        <div className="hackathon-logo-box">
                            <div className="ai-bharat-badge">
                                <div className="ai-bharat-label">Powered by</div>
                                <div className="ai-bharat-name">AI4Bharat</div>
                                <div className="ai-bharat-sub">IndicNLP · IndicWav2Vec</div>
                            </div>
                            <div className="ai-bharat-badge">
                                <div className="ai-bharat-label">Ministry</div>
                                <div className="ai-bharat-name">MeitY</div>
                                <div className="ai-bharat-sub">Govt. of India</div>
                            </div>
                            <div className="ai-bharat-badge"
                                style={{background: "rgba(255,153,51,0.1)", borderColor: "rgba(255,153,51,0.3)"}}>
                                <div className="ai-bharat-label">Theme</div>
                                <div className="ai-bharat-name" style={{color: "var(--saffron-light)"}}>12</div>
                                <div className="ai-bharat-sub">1092 Helpline AI</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="hackathon-cards">
                <div className="h-card fade-up">
                    <div className="h-card-icon">
                        <span className="material-symbols-outlined"
                            style={{fontVariationSettings: "'FILL' 1", color: "var(--navy)"}}>record_voice_over</span>
                    </div>
                    <div className="h-card-title">Voice-to-Voice AI Pipeline</div>
                    <div className="h-card-desc">End-to-end real-time pipeline from citizen speech to structured ticket,
                        with multi-stage AI processing and sub-2-second latency. Built on free-tier APIs for hackathon
                        viability.</div>
                    <div className="h-tags">
                        <span className="h-tag">Faster-Whisper</span>
                        <span className="h-tag">Groq API</span>
                        <span className="h-tag">Gemini Flash</span>
                        <span className="h-tag">gTTS</span>
                    </div>
                </div>
                <div className="h-card fade-up">
                    <div className="h-card-icon">
                        <span className="material-symbols-outlined"
                            style={{fontVariationSettings: "'FILL' 1", color: "var(--saffron)"}}>storage</span>
                    </div>
                    <div className="h-card-title">RAG-Powered Case Memory</div>
                    <div className="h-card-desc">ChromaDB / FAISS vector store indexes past confirmed cases with PII
                        anonymisation. Semantic similarity search retrieves historical resolutions to augment LLM output
                        — improving speed, precision, and accuracy.</div>
                    <div className="h-tags">
                        <span className="h-tag">ChromaDB</span>
                        <span className="h-tag">FAISS</span>
                        <span className="h-tag">Embeddings</span>
                        <span className="h-tag">Async write-back</span>
                    </div>
                </div>
                <div className="h-card fade-up">
                    <div className="h-card-icon">
                        <span className="material-symbols-outlined"
                            style={{fontVariationSettings: "'FILL' 1", color: "var(--green-india)"}}>language</span>
                    </div>
                    <div className="h-card-title">Indic Language Specialisation</div>
                    <div className="h-card-desc">AI4Bharat IndicWav2Vec and Parler-TTS for Kannada-first processing.
                        fastText dialect detection with regional cluster tagging ensures dialect-aware retrieval and
                        synthesis across Karnataka's diverse linguistics.</div>
                    <div className="h-tags">
                        <span className="h-tag">AI4Bharat</span>
                        <span className="h-tag">IndicWav2Vec</span>
                        <span className="h-tag">Parler-TTS</span>
                        <span className="h-tag">fastText</span>
                    </div>
                </div>
            </div>
        </div>
    </section>

    {/* ═══════════════════════════════════════
     FAQ
═══════════════════════════════════════ */}
    <section className="faq-section" id="faq">
        <div className="container">
            <div className="section-eyebrow fade-up">
                <div className="eyebrow-line"></div>
                <div className="eyebrow-text">Frequently Asked Questions</div>
            </div>
            <h2 className="section-title fade-up">Common Questions</h2>
            <p className="section-desc fade-up">For technical queries, contact the DPAR (e-Governance) helpdesk at
                helpdesk@dpar.kar.gov.in</p>

            <div className="faq-grid" style={{marginTop: "48px"}}>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">What is Sahayak 1092 and who operates it?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">Sahayak 1092 is an AI-assisted voice helpline portal operated by the Department
                        of Personnel and Administrative Reforms (e-Governance), Government of Karnataka. It serves as
                        the digital interface for the 1092 Women Helpline, enabling citizens to report issues and
                        receive assistance across Kannada, Hindi, and English.</div>
                </div>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">How does the AI ensure it has understood my issue correctly?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">The system includes a mandatory Verification Loop (Stage 4). After interpreting
                        your complaint, the AI speaks back a summary and asks you to confirm with ಹೌದು/हाँ/Yes or
                        ಇಲ್ಲ/नहीं/No. No action is taken until your issue is confirmed — correct understanding is
                        prioritised over speed.</div>
                </div>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">What happens if the AI cannot understand my dialect or language?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">If the AI's confidence score falls below 0.75 or repeated misunderstanding
                        occurs, the system automatically escalates to a human officer — seamlessly, without friction.
                        The officer receives full call context to continue from where the AI stopped. No call is left
                        unattended.</div>
                </div>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">What is the RAG system and how does it help?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">RAG (Retrieval-Augmented Generation) is an additional stage (3.5) where the
                        system checks a vector database of past confirmed cases. If a similar case exists, the
                        historical resolution is retrieved and merged with the current AI summary — producing faster,
                        more accurate responses for common or repeated issue patterns. All stored data is
                        PII-anonymised.</div>
                </div>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">Is my personal data safe when calling 1092?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">Yes. All calls are processed with PII masking and encrypted in transit. Data
                        stored in the RAG vector database is fully anonymised — names, phone numbers, and specific
                        addresses are stripped before indexing. The system complies with the IT Act 2000 and DPDP Act
                        2023 guidelines.</div>
                </div>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">Which languages and dialects are supported?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">The system currently supports Kannada (including regional dialects such as
                        Mysuru, Dharwad, Udupi, and North Karnataka varieties), Hindi, and English. Beta support is
                        underway for Tulu, Kodava, and Konkani. The architecture is designed for extension to all 22
                        Scheduled Languages of India.</div>
                </div>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">How do officers use the AI-generated summaries?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">Officers see a live dashboard with the transcript, AI summary,
                        emotion/urgency/confidence tags, and RAG-matched case history. They can Confirm, Edit, or Reject
                        the AI summary — and take over the call at any moment. All corrections are fed back into the
                        system for continuous improvement.</div>
                </div>

                <div className="faq-item" onClick={(e) => toggleFaq(e.currentTarget as HTMLElement)}>
                    <div className="faq-q">
                        <div className="faq-q-text">What is the expected response latency of the AI system?</div>
                        <span className="material-symbols-outlined faq-icon">expand_more</span>
                    </div>
                    <div className="faq-a">The full pipeline (STT → Language ID → LLM interpretation → RAG lookup →
                        Verification TTS) completes in under 2–3 seconds per loop. On RAG cache hits (similarity score
                        above 0.85), latency can drop below 1 second. Pre-generated TTS phrases for common confirmations
                        achieve zero additional latency.</div>
                </div>

            </div>
        </div>
    </section>

    {/* ═══════════════════════════════════════
     TESTIMONIALS
═══════════════════════════════════════ */}
    <section className="testimonials-section">
        <div className="container">
            <div className="section-eyebrow fade-up">
                <div className="eyebrow-line" style={{background: "var(--green-india)"}}></div>
                <div className="eyebrow-text" style={{color: "var(--green-india)"}}>Testimonials</div>
            </div>
            <h2 className="section-title fade-up">Voices from the Field</h2>
            <p className="section-desc fade-up">Feedback from officers, officials, and community coordinators during the
                Sahayak 1092 pilot programme across Karnataka.</p>

            <div className="testi-grid">

                <div className="testi-card fade-up">
                    <div className="testi-badge">Response Officer · Bengaluru Urban</div>
                    <div className="testi-quote">The AI summary arrives before I even pick up the call context. Knowing the
                        urgency score and emotion state upfront lets me respond with the right tone immediately. The
                        Kannada dialect detection is genuinely impressive — even Dharwad accent variations are handled
                        well.</div>
                    <div className="testi-author">
                        <div className="testi-avatar">PS</div>
                        <div>
                            <div className="testi-name">Priya Subramaniam</div>
                            <div className="testi-role">Senior Response Officer, DPAR Karnataka</div>
                            <div className="testi-stars">
                                <span className="star">★</span><span className="star">★</span><span className="star">★</span><span
                                    className="star">★</span><span className="star">★</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="testi-card fade-up">
                    <div className="testi-badge">District Coordinator · Mysuru</div>
                    <div className="testi-quote">Before this system, our officers were spending 40–60 seconds just trying to
                        understand what the caller was saying across dialects. Now, verified understanding happens in
                        under 3 seconds and the officer gets a clean English summary with full context. Efficiency has
                        improved significantly.</div>
                    <div className="testi-author">
                        <div className="testi-avatar">RK</div>
                        <div>
                            <div className="testi-name">Rajesh Kumar Gowda</div>
                            <div className="testi-role">District Emergency Coordinator, Mysuru</div>
                            <div className="testi-stars">
                                <span className="star">★</span><span className="star">★</span><span className="star">★</span><span
                                    className="star">★</span><span className="star">★</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="testi-card fade-up">
                    <div className="testi-badge">Caller Feedback · Dharwad</div>
                    <div className="testi-quote">I called in my North Karnataka dialect — which usually confuses operators
                        from Bengaluru. The system understood me perfectly, repeated my issue back correctly, and
                        connected me to the officer within seconds. I didn't have to repeat myself even once. That
                        itself was a relief.</div>
                    <div className="testi-author">
                        <div className="testi-avatar" style={{background: "var(--green-india)"}}>LM</div>
                        <div>
                            <div className="testi-name">Lakshmi Madar</div>
                            <div className="testi-role">Citizen, Dharwad District</div>
                            <div className="testi-stars">
                                <span className="star">★</span><span className="star">★</span><span className="star">★</span><span
                                    className="star">★</span><span className="star">★</span>
                            </div>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </section>

    {/* ═══════════════════════════════════════
     FOOTER
═══════════════════════════════════════ */}
    <footer>
        <div className="tricolour-bar"></div>

        <div className="digital-india-strip">
            <div className="di-inner container">
                <span className="di-logo">
                    <span className="material-symbols-outlined"
                        style={{fontSize: "18px", fontVariationSettings: "'FILL' 1", color: "#4ade80"}}>public</span>
                    Digital India
                </span>
                <span className="di-sep">|</span>
                <span className="di-logo">
                    <span className="material-symbols-outlined"
                        style={{fontSize: "18px", fontVariationSettings: "'FILL' 1", color: "#60a5fa"}}>smart_toy</span>
                    AI4Bharat
                </span>
                <span className="di-sep">|</span>
                <span className="di-logo">
                    <span className="material-symbols-outlined"
                        style={{fontSize: "18px", fontVariationSettings: "'FILL' 1", color: "#fbbf24"}}>security</span>
                    MyGov.in
                </span>
                <span className="di-sep">|</span>
                <span className="di-logo">
                    <span className="material-symbols-outlined"
                        style={{fontSize: "18px", fontVariationSettings: "'FILL' 1", color: "#f87171"}}>gavel</span>
                    DPAR Karnataka
                </span>
                <span className="di-sep">|</span>
                <span className="di-logo">
                    <span className="material-symbols-outlined"
                        style={{fontSize: "18px", fontVariationSettings: "'FILL' 1", color: "#a78bfa"}}>shield</span>
                    NIC · National Informatics Centre
                </span>
            </div>
        </div>

        <div className="footer-top">
            <div className="container">
                <div className="footer-grid">
                    <div className="footer-brand-col">
                        <div className="footer-logo-row">
                            <svg width="48" height="48" viewBox="0 0 100 110" fill="none">
                                <circle cx="50" cy="46" r="40" stroke="#C8A951" strokeWidth="1.5" fill="none"
                                    opacity="0.5" />
                                <circle cx="50" cy="46" r="7" fill="#C8A951" opacity="0.8" />
                                <g opacity="0.6">
                                    <line x1="50" y1="39" x2="50" y2="12" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="50" y1="53" x2="50" y2="80" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="61" y1="42" x2="84" y2="30" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="39" y1="50" x2="16" y2="62" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="61" y1="50" x2="84" y2="62" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="39" y1="42" x2="16" y2="30" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="57" y1="38" x2="75" y2="18" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="43" y1="54" x2="25" y2="74" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="57" y1="54" x2="75" y2="74" stroke="#C8A951" strokeWidth="1.2" />
                                    <line x1="43" y1="38" x2="25" y2="18" stroke="#C8A951" strokeWidth="1.2" />
                                </g>
                                <rect x="30" y="78" width="40" height="4" rx="1" fill="#C8A951" opacity="0.7" />
                            </svg>
                            <div>
                                <div className="footer-brand-name">Sahayak 1092</div>
                                <div className="footer-brand-dept">Government of Karnataka</div>
                            </div>
                        </div>
                        <div className="footer-tagline">
                            The official AI-powered intelligence portal for the 1092 Women Helpline — providing
                            automated multilingual voice interpretation, dialect-aware analysis, and rule-based verified
                            understanding for emergency response.
                        </div>
                        <div className="footer-govt-badges">
                            <div className="footer-badge">
                                <span className="material-symbols-outlined"
                                    style={{fontSize: "14px", color: "var(--saffron-light)"}}>verified</span>
                                IT Act 2000 Compliant
                            </div>
                            <div className="footer-badge">
                                <span className="material-symbols-outlined"
                                    style={{fontSize: "14px", color: "var(--saffron-light)"}}>lock</span>
                                DPDP Act 2023
                            </div>
                            <div className="footer-badge">
                                <span className="material-symbols-outlined"
                                    style={{fontSize: "14px", color: "var(--saffron-light)"}}>cloud</span>
                                NIC Hosted
                            </div>
                            <div className="footer-badge">
                                <span className="material-symbols-outlined"
                                    style={{fontSize: "14px", color: "var(--saffron-light)"}}>access_time</span>
                                24/7 Active
                            </div>
                        </div>
                    </div>

                    <div>
                        <div className="footer-col-title">Quick Navigation</div>
                        <ul className="footer-links">
                            <li><a href="#home">Home</a></li>
                            <li><a href="/dashboard">Officer Dashboard</a></li>
                            <li><a href="#process">System Workflow</a></li>
                            <li><a href="#hackathon">Hackathon</a></li>
                            <li><a href="#faq">FAQ</a></li>
                            <li><a href="#">Training Resources</a></li>
                        </ul>
                    </div>

                    <div>
                        <div className="footer-col-title">Official Links</div>
                        <ul className="footer-links">
                            <li><a href="https://dpar.karnataka.gov.in" target="_blank">DPAR Karnataka</a></li>
                            <li><a href="https://www.india.gov.in" target="_blank">India.gov.in</a></li>
                            <li><a href="https://digitalindia.gov.in" target="_blank">Digital India</a></li>
                            <li><a href="https://www.meity.gov.in" target="_blank">MeitY</a></li>
                            <li><a href="https://ai4bharat.iitm.ac.in" target="_blank">AI4Bharat</a></li>
                            <li><a href="https://www.mygov.in" target="_blank">MyGov.in</a></li>
                        </ul>
                    </div>

                    <div>
                        <div className="footer-col-title">Emergency Contacts</div>
                        <ul className="footer-links">
                            <li><a href="tel:1092">1092 · Women Helpline</a></li>
                            <li><a href="tel:112">112 · National Emergency</a></li>
                            <li><a href="tel:100">100 · Police</a></li>
                            <li><a href="tel:108">108 · Ambulance</a></li>
                            <li><a href="tel:101">101 · Fire</a></li>
                            <li><a href="tel:1098">1098 · Child Helpline</a></li>
                        </ul>
                        <div
                            style={{marginTop: "20px", padding: "12px", background: "rgba(206,17,38,0.1)", border: "1px solid rgba(206,17,38,0.2)"}}>
                            <div
                                style={{fontSize: "10px", color: "rgba(255,255,255,0.4)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "6px"}}>
                                Technical Helpdesk</div>
                            <div style={{fontSize: "12px", color: "rgba(255,255,255,0.65)"}}>helpdesk@dpar.kar.gov.in</div>
                            <div style={{fontSize: "11px", color: "rgba(255,255,255,0.35)", marginTop: "2px"}}>Mon–Fri ·
                                9:30am–6:00pm IST</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div className="footer-bottom">
            <div className="container footer-bottom-inner">
                <div className="footer-legal">
                    © 2025 Department of Personnel &amp; Administrative Reforms (e-Governance), Government of
                    Karnataka.<br />
                    All Rights Reserved. Content owned and maintained by DPAR Karnataka.
                </div>
                <div className="footer-policy-links">
                    <a href="#">Privacy Policy</a>
                    <a href="#">Terms of Use</a>
                    <a href="#">Accessibility</a>
                    <a href="#">Sitemap</a>
                    <a href="#">RTI</a>
                    <a href="#">Disclaimer</a>
                </div>
            </div>
        </div>
    </footer>

    {/* ═══════════════════════════════════════
     JAVASCRIPT
═══════════════════════════════════════ */}
    

    </>
  );
}
