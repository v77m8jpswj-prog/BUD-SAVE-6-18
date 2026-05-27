import { useEffect, useState, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import {
  Hammer,
  Mail,
  Send,
  RefreshCw,
  Copy,
  Check,
  Inbox,
  ArrowUpRight,
  Settings,
  Radio,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function CopyChip({ value, label }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch (e) {}
  };
  return (
    <button
      onClick={onCopy}
      data-testid={`copy-${label}-btn`}
      className="bud-btn-ghost px-2 py-1 text-xs rounded inline-flex items-center gap-1.5"
      title={`Copy ${label}`}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? "copied" : "copy"}
    </button>
  );
}

function StatusPill({ ok, label }) {
  return (
    <div
      className="inline-flex items-center gap-2 text-xs px-2 py-1 rounded"
      style={{
        background: ok ? "rgba(132,204,22,0.08)" : "rgba(239,68,68,0.08)",
        border: `1px solid ${ok ? "rgba(132,204,22,0.3)" : "rgba(239,68,68,0.3)"}`,
        color: ok ? "var(--bud-green)" : "var(--bud-red)",
      }}
      data-testid={`status-pill-${label}`}
    >
      <span
        className={ok ? "bud-pulse-dot" : ""}
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: ok ? "var(--bud-green)" : "var(--bud-red)",
        }}
      />
      <span className="uppercase tracking-wider">{label}</span>
    </div>
  );
}

function Section({ title, kicker, right, children }) {
  return (
    <section className="bud-card p-5 fade-in" data-testid={`section-${title.toLowerCase().replace(/\s+/g,'-')}`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          {kicker && (
            <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)] mb-1">
              {kicker}
            </div>
          )}
          <h2 className="bud-display text-xl text-[var(--bud-text)]">{title}</h2>
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

function App() {
  const [health, setHealth] = useState(null);
  const [config, setConfig] = useState(null);
  const [letters, setLetters] = useState([]);
  const [baseUrlInput, setBaseUrlInput] = useState("");
  const [nineTokenInput, setNineTokenInput] = useState("");
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeTo, setComposeTo] = useState("og");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeRound, setComposeRound] = useState(1);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = (msg, kind = "ok") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 2400);
  };

  const refresh = useCallback(async () => {
    try {
      const [h, c, l] = await Promise.all([
        axios.get(`${API}/health`),
        axios.get(`${API}/agent-mail/config`),
        axios.get(`${API}/agent-mail/letters?limit=100`),
      ]);
      setHealth(h.data);
      setConfig(c.data);
      setLetters(l.data.letters || []);
      if (!baseUrlInput && c.data.bud_base_url) setBaseUrlInput(c.data.bud_base_url);
    } catch (e) {
      console.error("refresh failed", e);
      showToast("backend unreachable", "err");
    }
  }, [baseUrlInput]);

  useEffect(() => {
    // Auto-fill base URL from frontend env if config doesn't have one yet
    if (!baseUrlInput && BACKEND_URL) setBaseUrlInput(BACKEND_URL);
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, []); // eslint-disable-line

  const saveConfig = async () => {
    setBusy(true);
    try {
      const payload = {};
      if (baseUrlInput) payload.bud_base_url = baseUrlInput;
      if (nineTokenInput) payload.nine_outbound_token = nineTokenInput;
      await axios.post(`${API}/agent-mail/configure`, payload);
      setNineTokenInput("");
      await refresh();
      showToast("config saved");
    } catch (e) {
      showToast("save failed", "err");
    } finally {
      setBusy(false);
    }
  };

  const fireHandshake = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/agent-mail/handshake`);
      if (r.data.ok) showToast("handshake delivered to OG");
      else showToast(`handshake: ${r.data.letter?.delivery_status || "failed"}`, "err");
      await refresh();
    } catch (e) {
      showToast(e.response?.data?.detail || "handshake failed", "err");
    } finally {
      setBusy(false);
    }
  };

  const sendCompose = async () => {
    if (!composeSubject.trim() || !composeBody.trim()) {
      showToast("subject + body required", "err");
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/agent-mail/send`, {
        to_agent: composeTo,
        subject: composeSubject,
        body: composeBody,
        body_format: "markdown",
        round: Number(composeRound) || 1,
      });
      if (r.data.ok) {
        showToast(`sent to ${composeTo}`);
        setComposeSubject("");
        setComposeBody("");
        setComposeOpen(false);
      } else {
        showToast(`send: ${r.data.letter?.delivery_status || "failed"}`, "err");
      }
      await refresh();
    } catch (e) {
      showToast(e.response?.data?.detail || "send failed", "err");
    } finally {
      setBusy(false);
    }
  };

  const inboxOK = !!(config && config.bud_base_url);
  const ogReady = !!(config && config.og_outbound_token_set);
  const nineReady = !!(config && config.nine_outbound_token_set);
  const handshakeSent = !!(config && config.handshake_sent_at);

  const renderLetter = (l) => {
    const outbound = l.direction === "outbound";
    return (
      <div
        key={l.id}
        className="bud-card-inset p-4 fade-in"
        data-testid={`letter-${l.id}`}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className="text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded"
              style={{
                background: outbound ? "rgba(245,158,11,0.12)" : "rgba(132,204,22,0.1)",
                color: outbound ? "var(--bud-amber)" : "var(--bud-green)",
                border: `1px solid ${outbound ? "rgba(245,158,11,0.3)" : "rgba(132,204,22,0.25)"}`,
              }}
            >
              {outbound ? (
                <span className="inline-flex items-center gap-1"><ArrowUpRight size={10}/> bud → {l.to_agent}</span>
              ) : (
                <span className="inline-flex items-center gap-1"><Inbox size={10}/> {l.from_agent} → bud</span>
              )}
            </span>
            <span className="text-[10px] text-[var(--bud-muted)]">R{l.round}</span>
            {outbound && (
              <span className="text-[10px] text-[var(--bud-muted)]">
                · {l.delivery_status}
              </span>
            )}
          </div>
          <span className="text-[10px] text-[var(--bud-muted)] whitespace-nowrap">
            {new Date(l.received_at || l.sent_at).toLocaleString()}
          </span>
        </div>
        <div className="text-sm text-[var(--bud-text)] font-semibold mb-1.5 truncate">
          {l.subject}
        </div>
        <pre className="text-xs text-[var(--bud-muted)] whitespace-pre-wrap break-words leading-relaxed max-h-48 overflow-auto">
{l.body}
        </pre>
      </div>
    );
  };

  return (
    <div className="App min-h-screen bg-[var(--bud-bg)] text-[var(--bud-text)]">
      {/* Header */}
      <header className="border-b border-[var(--bud-line)] bud-grain" data-testid="app-header">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-sm flex items-center justify-center"
              style={{
                background: "linear-gradient(135deg, var(--bud-amber) 0%, var(--bud-rust) 100%)",
                boxShadow: "0 0 24px var(--bud-amber-glow)",
              }}
            >
              <Hammer size={20} color="#0a0a0b" strokeWidth={2.5} />
            </div>
            <div>
              <div className="bud-display text-2xl leading-none">BUD</div>
              <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)] mt-1">
                DOC HOLMES · PERSONAL FOREMAN
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusPill ok={health?.mongo} label="mongo" />
            <StatusPill ok={inboxOK} label="inbox" />
            <StatusPill ok={handshakeSent} label="og" />
            <button
              onClick={refresh}
              className="bud-btn-ghost p-2 rounded ml-1"
              title="refresh"
              data-testid="refresh-btn"
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-3 gap-6 stagger">
        {/* LEFT — Identity / inbox creds */}
        <div className="lg:col-span-2 space-y-6">
          <Section
            title="The Pipe"
            kicker="DAY 1 / NODE BOOT"
            right={
              <button
                onClick={fireHandshake}
                disabled={busy || !inboxOK}
                className="bud-btn-primary px-4 py-2 rounded text-sm inline-flex items-center gap-2"
                data-testid="fire-handshake-btn"
              >
                <Radio size={14} />
                {handshakeSent ? "Re-send handshake" : "Fire handshake → OG"}
              </button>
            }
          >
            {!inboxOK && (
              <div className="bud-card-inset p-3 mb-4 text-xs text-[var(--bud-amber)] border-[var(--bud-amber)]" style={{borderColor:'rgba(245,158,11,0.4)'}}>
                Set your <code>bud_base_url</code> below before firing the handshake. Without it, OG can't reach back.
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">
                  BUD INBOX URL
                </div>
                <div className="bud-card-inset px-3 py-2.5 flex items-center justify-between gap-2">
                  <code className="text-xs text-[var(--bud-text)] truncate" data-testid="bud-inbox-url">
                    {config?.bud_inbox_url || "—  set base URL ↓"}
                  </code>
                  {config?.bud_inbox_url && <CopyChip value={config.bud_inbox_url} label="inbox-url" />}
                </div>
              </div>
              <div>
                <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">
                  BUD INBOUND TOKEN  <span className="text-[var(--bud-amber)]">(give to OG)</span>
                </div>
                <div className="bud-card-inset px-3 py-2.5 flex items-center justify-between gap-2">
                  <code className="text-xs text-[var(--bud-text)] truncate" data-testid="bud-inbound-token">
                    {config?.bud_inbound_token || "…"}
                  </code>
                  {config?.bud_inbound_token && <CopyChip value={config.bud_inbound_token} label="inbound-token" />}
                </div>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-3 gap-3 text-xs">
              <div className="bud-card-inset p-3">
                <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1">OG</div>
                <div className="text-[var(--bud-text)] truncate">{config?.og_inbox_url ? "ready" : "—"}</div>
                <div className="text-[10px] text-[var(--bud-muted)] mt-1">
                  outbound token: {ogReady ? <span className="text-[var(--bud-green)]">loaded</span> : <span className="text-[var(--bud-red)]">missing</span>}
                </div>
              </div>
              <div className="bud-card-inset p-3">
                <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1">9 (WRENCH)</div>
                <div className="text-[var(--bud-text)] truncate">{config?.nine_inbox_url ? "URL set" : "—"}</div>
                <div className="text-[10px] text-[var(--bud-muted)] mt-1">
                  outbound token: {nineReady ? <span className="text-[var(--bud-green)]">loaded</span> : <span className="text-[var(--bud-amber)]">waiting on OG shuttle</span>}
                </div>
              </div>
              <div className="bud-card-inset p-3">
                <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1">HANDSHAKE</div>
                <div className="text-[var(--bud-text)] truncate" data-testid="handshake-status">
                  {handshakeSent ? "delivered" : "pending"}
                </div>
                <div className="text-[10px] text-[var(--bud-muted)] mt-1">
                  {handshakeSent ? new Date(config.handshake_sent_at).toLocaleString() : "not yet"}
                </div>
              </div>
            </div>
          </Section>

          <Section
            title="Mailroom"
            kicker={`LETTERS · ${letters.length}`}
            right={
              <button
                onClick={() => setComposeOpen((v) => !v)}
                className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                data-testid="compose-btn"
              >
                <Mail size={14} /> {composeOpen ? "close" : "compose"}
              </button>
            }
          >
            {composeOpen && (
              <div className="bud-card-inset p-4 mb-4 space-y-3" data-testid="compose-panel">
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-[var(--bud-muted)] tracking-widest">TO</span>
                  <div className="flex gap-2">
                    {["og", "nine"].map((agent) => (
                      <button
                        key={agent}
                        onClick={() => setComposeTo(agent)}
                        className="px-3 py-1 rounded text-xs uppercase tracking-wider"
                        data-testid={`compose-to-${agent}`}
                        style={{
                          background: composeTo === agent ? "var(--bud-amber)" : "transparent",
                          color: composeTo === agent ? "#0a0a0b" : "var(--bud-text)",
                          border: `1px solid ${composeTo === agent ? "var(--bud-amber)" : "var(--bud-line)"}`,
                        }}
                      >
                        {agent}
                      </button>
                    ))}
                  </div>
                  <span className="text-[var(--bud-muted)] tracking-widest ml-3">ROUND</span>
                  <input
                    type="number"
                    min={1}
                    value={composeRound}
                    onChange={(e) => setComposeRound(e.target.value)}
                    className="bud-input px-2 py-1 rounded w-16 text-xs"
                    data-testid="compose-round-input"
                  />
                </div>
                <input
                  type="text"
                  placeholder="subject (< 80 chars, topic + status)"
                  value={composeSubject}
                  onChange={(e) => setComposeSubject(e.target.value)}
                  maxLength={120}
                  className="bud-input w-full px-3 py-2 rounded text-sm"
                  data-testid="compose-subject-input"
                />
                <textarea
                  placeholder="markdown body. surgical. headers, bullets, code blocks. no long prose."
                  value={composeBody}
                  onChange={(e) => setComposeBody(e.target.value)}
                  rows={8}
                  className="bud-input w-full px-3 py-2 rounded text-sm leading-relaxed"
                  data-testid="compose-body-input"
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setComposeOpen(false)}
                    className="bud-btn-ghost px-3 py-2 rounded text-sm"
                    data-testid="compose-cancel-btn"
                  >
                    cancel
                  </button>
                  <button
                    onClick={sendCompose}
                    disabled={busy}
                    className="bud-btn-primary px-4 py-2 rounded text-sm inline-flex items-center gap-2"
                    data-testid="compose-send-btn"
                  >
                    <Send size={14} /> send
                  </button>
                </div>
              </div>
            )}

            {letters.length === 0 ? (
              <div className="text-xs text-[var(--bud-muted)] py-8 text-center">
                no letters yet. fire the handshake when ready.
              </div>
            ) : (
              <div className="space-y-3 max-h-[600px] overflow-auto pr-1">
                {letters.map(renderLetter)}
              </div>
            )}
          </Section>
        </div>

        {/* RIGHT — config + roadmap */}
        <div className="space-y-6">
          <Section title="Wiring" kicker="CONFIG">
            <div className="space-y-3">
              <div>
                <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">
                  BUD BASE URL
                </div>
                <input
                  type="text"
                  placeholder="https://your-bud.preview.emergentagent.com"
                  value={baseUrlInput}
                  onChange={(e) => setBaseUrlInput(e.target.value)}
                  className="bud-input w-full px-3 py-2 rounded text-xs"
                  data-testid="base-url-input"
                />
                <div className="text-[10px] text-[var(--bud-muted)] mt-1">
                  pre-filled from frontend env. confirm + save.
                </div>
              </div>
              <div>
                <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">
                  9'S OUTBOUND TOKEN  <span className="text-[var(--bud-muted)]">(when OG shuttles it)</span>
                </div>
                <input
                  type="text"
                  placeholder="paste when received"
                  value={nineTokenInput}
                  onChange={(e) => setNineTokenInput(e.target.value)}
                  className="bud-input w-full px-3 py-2 rounded text-xs"
                  data-testid="nine-token-input"
                />
              </div>
              <button
                onClick={saveConfig}
                disabled={busy}
                className="bud-btn-primary w-full px-3 py-2 rounded text-sm inline-flex items-center justify-center gap-2"
                data-testid="save-config-btn"
              >
                <Settings size={14} /> save wiring
              </button>
            </div>
          </Section>

          <Section title="Roadmap" kicker="WHAT'S NEXT">
            <ul className="space-y-2.5 text-xs">
              {[
                ["D1", "Backend up · inbox live · handshake to OG", true],
                ["D2", "Outlook (Microsoft Graph) OAuth + inbox read/draft/send", false],
                ["D2", "AutoLEAP read-only board (ROs, estimates, unpaid)", false],
                ["D2", "Daily 7 AM briefing → doc@drunderhood.com", false],
                ["D3", "Voice I/O — Whisper + TTS, push-to-talk", false],
                ["D3", "Brain client to 9's /api/brain/*", false],
              ].map(([phase, text, done], i) => (
                <li key={i} className="flex items-start gap-3" data-testid={`roadmap-item-${i}`}>
                  <span
                    className="text-[10px] tracking-widest px-1.5 py-0.5 rounded mt-0.5"
                    style={{
                      background: done ? "rgba(132,204,22,0.1)" : "transparent",
                      color: done ? "var(--bud-green)" : "var(--bud-muted)",
                      border: `1px solid ${done ? "rgba(132,204,22,0.25)" : "var(--bud-line)"}`,
                    }}
                  >
                    {phase}
                  </span>
                  <span className={done ? "text-[var(--bud-text)]" : "text-[var(--bud-muted)]"}>
                    {text}
                  </span>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Memory" kicker="ON DISK">
            <ul className="text-xs space-y-1.5 text-[var(--bud-muted)]">
              {(health?.memory_files || []).map((f) => (
                <li key={f} className="flex items-center gap-2" data-testid={`memory-file-${f}`}>
                  <span className="w-1 h-1 rounded-full bg-[var(--bud-amber)]" />
                  <code className="text-[var(--bud-text)]">/app/memory/{f}</code>
                </li>
              ))}
              {(!health?.memory_files || health.memory_files.length === 0) && (
                <li>no memory files yet</li>
              )}
            </ul>
          </Section>
        </div>
      </main>

      <footer className="max-w-6xl mx-auto px-6 py-8 text-[10px] tracking-[0.3em] text-[var(--bud-muted)] uppercase">
        <Hammer size={12} className="inline mr-2" /> Bud · third node · for Doc only · no upsell · no fluff
      </footer>

      {toast && (
        <div
          className="fixed bottom-6 right-6 px-4 py-3 rounded bud-card text-sm fade-in"
          style={{
            borderColor: toast.kind === "err" ? "var(--bud-red)" : "var(--bud-green)",
            color: toast.kind === "err" ? "var(--bud-red)" : "var(--bud-green)",
          }}
          data-testid="toast"
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}

export default App;
