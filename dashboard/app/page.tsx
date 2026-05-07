"use client";

import { useRouter } from "next/navigation";
import { Shield, ArrowRight, CheckCircle, Zap, Users, Phone, BookOpen, AlertTriangle, HeartPulse } from "lucide-react";

// ── Indian Flag SVG (proper tricolour with Ashoka Chakra) ──
function IndiaFlag() {
  return (
    <svg
      width="42"
      height="28"
      viewBox="0 0 900 600"
      xmlns="http://www.w3.org/2000/svg"
      className="rounded-sm shadow-sm border border-black/10"
      aria-label="Flag of India"
    >
      {/* Three horizontal bands */}
      <rect width="900" height="200" fill="#FF9933" />
      <rect y="200" width="900" height="200" fill="#FFFFFF" />
      <rect y="400" width="900" height="200" fill="#138808" />
      {/* Ashoka Chakra – 24-spoke navy wheel centred in white band */}
      <g transform="translate(450,300)">
        {/* Outer ring */}
        <circle cx="0" cy="0" r="90" fill="none" stroke="#000080" strokeWidth="10" />
        <circle cx="0" cy="0" r="10" fill="#000080" />
        {/* 24 spokes */}
        {Array.from({ length: 24 }).map((_, i) => {
          const angle = (i * 360) / 24;
          const rad = (angle * Math.PI) / 180;
          const x2 = Math.round(80 * Math.sin(rad));
          const y2 = Math.round(-80 * Math.cos(rad));
          return (
            <line
              key={i}
              x1="0"
              y1="0"
              x2={x2}
              y2={y2}
              stroke="#000080"
              strokeWidth="6"
              strokeLinecap="round"
            />
          );
        })}
      </g>
    </svg>
  );
}

// ── Feature Card ──
function FeatureCard({
  icon,
  title,
  desc,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <div className="p-6 bg-white border border-[#dbc2b0]/40 rounded-3xl hover:shadow-md transition-shadow">
      <div className="w-10 h-10 bg-[#ffdcc2]/40 rounded-xl flex items-center justify-center mb-4 text-[#8f4e00]">
        {icon}
      </div>
      <div className="text-base font-semibold text-[#1a1c1e] mb-2">{title}</div>
      <div className="text-sm text-[#554336] leading-relaxed">{desc}</div>
    </div>
  );
}

// ── Resource Card ──
function ResourceCard({
  icon,
  title,
  desc,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <a
      href="#"
      className="group block p-8 bg-white border border-[#dbc2b0]/40 rounded-3xl hover:border-[#8f4e00]/30 hover:shadow-lg transition-all duration-300"
    >
      <div className="w-14 h-14 bg-[#f3f3f6] rounded-2xl flex items-center justify-center mb-6 group-hover:bg-[#ffdcc2]/30 transition-colors text-[#8f4e00]">
        {icon}
      </div>
      <h4 className="text-xl font-semibold text-[#1a1c1e] mb-3 group-hover:text-[#8f4e00] transition-colors">
        {title}
      </h4>
      <p className="text-[#554336] text-sm leading-relaxed">{desc}</p>
    </a>
  );
}

// ── Main Landing Page ──
export default function LandingPage() {
  const router = useRouter();

  const problems = [
    {
      n: 1,
      title: "Every Call Lands on a Human",
      desc: "Even simple requests — status updates, basic guidance, complaint registration — are manually handled, choking lines during real emergencies.",
    },
    {
      n: 2,
      title: "Dialect Barriers Break Communication",
      desc: "A citizen speaking rural Kannada or Bhojpuri struggles to be understood. Critical details get lost. Help arrives late or misinformed.",
    },
    {
      n: 3,
      title: "Citizens Repeat Themselves Every Time",
      desc: "No context is carried between interactions. Every transfer means starting over — exhausting for citizens already in distress.",
    },
    {
      n: 4,
      title: "Officers Burn Out on Routine Calls",
      desc: "80% of calls are routine. Officers spend their shift on repetitive queries instead of genuine emergencies that need human judgment.",
    },
  ];

  return (
    <div className="bg-[#f9f9fc] text-[#1a1c1e] font-[Public_Sans] antialiased min-h-screen flex flex-col">

      {/* ── TopAppBar ── */}
      <header className="flex justify-between items-center px-8 h-12 w-full fixed top-0 z-50 bg-white/90 backdrop-filter backdrop-blur-md border-b border-[#dbc2b0]/30">
        <div className="flex items-center gap-4 max-w-[1440px] mx-auto w-full justify-between">
          {/* Sahayak Logo – same SVG used in the Officer Command Center */}
          <div className="flex items-center gap-2">
            <img
              src="/sahayak_logo.svg"
              alt="Sahayak 1092"
              className="h-8 w-auto object-contain object-left"
            />
            <span className="text-base font-bold text-black tracking-tight">Sahayak 1092</span>
          </div>

          <div className="hidden md:flex items-center gap-2 px-4 py-1.5 bg-[#ffdad6]/40 border border-[#ba1a1a]/20 rounded-full">
            <span className="w-2 h-2 rounded-full bg-[#ba1a1a] animate-pulse shrink-0" />
            <span className="text-xs font-bold text-[#93000a] uppercase tracking-widest whitespace-nowrap">
              AI-First · Every Voice Heard · Every Second Counts
            </span>
          </div>

          {/* Right side */}
          <div className="flex items-center gap-4">
            <IndiaFlag />
            <div className="flex items-center gap-1.5 text-xs font-bold text-[#056e00] bg-[#8dfc75]/30 px-3 py-1 rounded-full">
              <CheckCircle size={13} />
              Secure Access
            </div>
          </div>
        </div>
      </header>

      <div className="flex flex-1 pt-[48px]">
        <main className="flex-1 w-full flex flex-col">

          {/* ── Hero Section ── */}
          <section
            className="w-full py-20 px-8 flex flex-col items-center justify-center text-center relative overflow-hidden border-b border-[#dbc2b0]/30"
            style={{
              backgroundImage: "url('/india_emergency_bg.png')",
              backgroundSize: "contain",
              backgroundPosition: "center",
              backgroundRepeat: "no-repeat",
              backgroundColor: "#07102a",
            }}
          >
            <div className="absolute inset-0 bg-black/55 z-0" />

            <div className="max-w-4xl mx-auto z-10 flex flex-col items-center relative">

              {/* Live badge */}
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-[#ffdad6] text-[#93000a] rounded-full mb-8 shadow-sm">
                <span className="w-2.5 h-2.5 rounded-full bg-[#ba1a1a] animate-pulse" />
                <span className="text-xs font-bold uppercase tracking-widest">
                  AI-First 1092 · Pan-India 24/7
                </span>
              </div>

              {/* Headline */}
              <h1 className="text-5xl md:text-6xl lg:text-7xl mb-6 leading-tight tracking-tight font-extrabold text-white">
                India's 1092 Helpline<br />Finally Works For Everyone
              </h1>

              {/* Sub */}
              <p className="text-xl md:text-2xl max-w-2xl mx-auto mb-4 text-white/90 leading-relaxed">
                Most 1092 calls go to a human even for routine help — causing delays, officer burnout, and citizens repeating themselves. Sahayak answers instantly, understands your dialect, solves your problem end-to-end.
              </p>

              {/* Stats strip */}
              <div className="flex items-center gap-6 mb-10 text-white/80">
                <div className="text-center">
                  <div className="text-2xl font-black text-white">2.4s</div>
                  <div className="text-xs font-semibold uppercase tracking-wider">AI picks up</div>
                </div>
                <div className="w-px h-10 bg-white/30" />
                <div className="text-center">
                  <div className="text-2xl font-black text-white">14+</div>
                  <div className="text-xs font-semibold uppercase tracking-wider">Indian languages</div>
                </div>
                <div className="w-px h-10 bg-white/30" />
                <div className="text-center">
                  <div className="text-2xl font-black text-white">~80%</div>
                  <div className="text-xs font-semibold uppercase tracking-wider">Calls auto-resolved</div>
                </div>
              </div>

              {/* CTA card */}
              <div className="w-full max-w-lg mx-auto bg-white p-6 rounded-3xl shadow-xl border border-[#dbc2b0]/50 relative group">
                <div className="absolute -inset-1 bg-gradient-to-r from-[#ba1a1a]/20 to-[#8f4e00]/20 rounded-3xl blur opacity-30 group-hover:opacity-50 transition duration-500" />

                <button className="relative w-full h-24 bg-[#ba1a1a] text-white rounded-2xl flex items-center justify-center gap-4 hover:bg-[#a31515] transition-all shadow-[0_8px_24px_rgba(186,26,26,0.3)] active:scale-[0.98] mb-4">
                  <span
                    className="material-symbols-outlined text-[48px]"
                    style={{ fontVariationSettings: '"FILL" 1' }}
                  >
                    call
                  </span>
                  <span className="text-4xl font-black tracking-tight">Call 1092 Now</span>
                </button>

                <button
                  type="button"
                  onClick={() => router.push("/dashboard")}
                  className="relative w-full h-12 bg-white border border-[#dbc2b0] text-[#1a1c1e] rounded-xl flex items-center justify-center gap-3 hover:bg-[#f3f3f6] transition-all text-sm font-semibold"
                >
                  Go to Officer Dashboard
                  <ArrowRight size={16} className="ml-1 text-[#887364]" />
                </button>

                <p className="text-xs text-[#887364] text-center mt-2">
                  Authorized government personnel only · Access is logged and audited.
                </p>
              </div>
            </div>
          </section>

          {/* ── Main Content ── */}
          <div className="max-w-[1440px] mx-auto w-full px-8 py-16">

            {/* ── Bento: Stat + Problem ── */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-8 mb-16">

              {/* Stat card */}
              <div className="md:col-span-4 bg-white border border-[#dbc2b0]/40 rounded-3xl p-8 flex flex-col justify-center items-center text-center shadow-sm hover:shadow-md transition-shadow">
                <div className="w-20 h-20 bg-[#8dfc75]/20 rounded-full flex items-center justify-center mb-6">
                  <span className="material-symbols-outlined text-[#056e00] text-[40px]">timer</span>
                </div>
                <h4 className="text-4xl font-black text-[#1a1c1e] mb-2">2.4 Sec</h4>
                <p className="text-xs font-bold uppercase tracking-wider text-[#554336] mb-6">
                  Average AI Response Time
                </p>
                <div className="px-4 py-2 bg-[#8dfc75] text-[#067500] rounded-full text-xs font-bold flex items-center gap-2">
                  <span
                    className="material-symbols-outlined text-[18px]"
                    style={{ fontVariationSettings: '"FILL" 1' }}
                  >
                    check_circle
                  </span>
                  System Live Nationwide
                </div>
              </div>

              {/* Problem section */}
              <div className="md:col-span-8 bg-white border border-[#dbc2b0]/40 rounded-3xl p-8 shadow-sm hover:shadow-md transition-shadow">
                <h3 className="text-2xl font-bold text-[#1a1c1e] mb-8 flex items-center gap-3">
                  <span className="material-symbols-outlined text-[#ba1a1a] text-3xl">
                    crisis_alert
                  </span>
                  The Problem We're Solving
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {problems.map(({ n, title, desc }) => (
                    <div key={n} className="flex gap-5">
                      <div className="w-10 h-10 rounded-full bg-[#ffdcc2]/40 text-[#8f4e00] flex items-center justify-center text-xl font-bold shrink-0">
                        {n}
                      </div>
                      <div>
                        <h4 className="text-lg font-semibold text-[#1a1c1e] mb-2">{title}</h4>
                        <p className="text-[#554336] text-sm leading-relaxed">{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ── How Sahayak Fixes This ── */}
            <div className="mb-16">
              <h3 className="text-2xl font-bold text-[#1a1c1e] mb-8">
                How Sahayak 1092 Fixes This
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <FeatureCard
                  icon={<Zap size={20} />}
                  title="Speaks Before You Ask"
                  desc="Sahayak detects your language and dialect in the first 2 seconds — Kannada, Hindi, Tamil, English — and responds naturally, like someone from your own community."
                />
                <FeatureCard
                  icon={<BookOpen size={20} />}
                  title="Understands, Then Acts"
                  desc="It doesn't just translate — it analyses your intent, urgency, and emotion. It dispatches help, registers complaints, and closes the call without a human in between."
                />
                <FeatureCard
                  icon={<Users size={20} />}
                  title="Learns From Every Officer"
                  desc="Every case a human officer resolves trains Sahayak to handle the same situation next time on its own. The system gets smarter with every call — reducing transfers continuously."
                />
                <FeatureCard
                  icon={<Phone size={20} />}
                  title="Warm Handover, Not Cold Drop"
                  desc="When Sahayak does transfer, the officer receives a full transcript, emotion flag, AI summary, and one-click actions. The citizen never repeats a word."
                />
              </div>
            </div>

            {/* ── Citizen Resources ── */}
            <div className="mb-4">
              <h3 className="text-2xl font-bold text-[#1a1c1e] mb-8">Citizen Resources</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <ResourceCard
                  icon={<HeartPulse size={28} />}
                  title="Find Nearest Emergency Hospital"
                  desc="Locate trauma centers, blood banks, and emergency rooms. Sahayak can auto-dispatch an ambulance before you even finish explaining."
                />
                <ResourceCard
                  icon={<Shield size={28} />}
                  title="Register a Complaint Instantly"
                  desc="No forms, no counters, no waiting. Speak your complaint to Sahayak and it's registered in the government system before the call ends."
                />
                <ResourceCard
                  icon={<AlertTriangle size={28} />}
                  title="Live Emergency Alerts"
                  desc="Active flood warnings, fire advisories, and civic alerts for your district — updated in real time and read aloud in your language on request."
                />
              </div>
            </div>

          </div>
        </main>
      </div>

      {/* ── Footer ── */}
      <footer className="w-full py-8 px-8 bg-[#eeeef0] border-t border-[#dbc2b0]/30 mt-auto">
        <div className="max-w-[1440px] mx-auto w-full flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-3">
            <Shield size={18} className="text-[#1a1c1e]" />
            <span className="text-lg font-bold text-[#1a1c1e]">
              Sahayak 1092 · Government of India
            </span>
          </div>
          <div className="text-sm text-[#554336] text-center md:text-left">
            © 2025 Government of India · Built for Bharat, in every language
          </div>
          <div className="flex gap-6 flex-wrap justify-center text-sm text-[#554336]">
            <a href="#" className="hover:text-[#8f4e00] transition-colors">Privacy Policy</a>
            <a href="#" className="hover:text-[#8f4e00] transition-colors">National Portal</a>
            <a href="#" className="hover:text-[#8f4e00] transition-colors">Terms of Use</a>
            <span className="text-[#887364]">
              Authorized personnel only · All access is monitored
            </span>
          </div>
        </div>
      </footer>

    </div>
  );
}