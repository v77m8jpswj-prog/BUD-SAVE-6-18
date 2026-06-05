import { useEffect, useRef, useState, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import VoicePanel from "./VoicePanel";
import VoiceRealtimePanel from "./VoiceRealtimePanel";
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
  Link2,
  Link2Off,
  ExternalLink,
  Paperclip,
  Clipboard,
  Archive,
  Package,
  Sunrise,
  Play,
  Clock,
  Mic,
  MicOff,
  Volume2,
  Trash2,
  Loader2,
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
  const [outlook, setOutlook] = useState(null);
  const [outlookMail, setOutlookMail] = useState([]);
  const [outlookLoading, setOutlookLoading] = useState(false);
  const [replyFor, setReplyFor] = useState(null);
  const [replyBody, setReplyBody] = useState("");
  const [assets, setAssets] = useState([]);
  const [copiedAssetId, setCopiedAssetId] = useState(null);
  const [briefing, setBriefing] = useState(null);
  const [briefingStatus, setBriefingStatus] = useState(null);
  const [briefingBusy, setBriefingBusy] = useState(false);
  const lastInboundIdRef = useRef(null);
  const lastInboundInitRef = useRef(false);
  const [sendOpen, setSendOpen] = useState(false);
  const [sendTo, setSendTo] = useState("");
  const [sendCc, setSendCc] = useState("");
  const [sendSubject, setSendSubject] = useState("");
  const [sendBody, setSendBody] = useState("");

  const showToast = (msg, kind = "ok") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 2400);
  };

  const refresh = useCallback(async () => {
    try {
      const [h, c, l, o, a, bL, bS] = await Promise.all([
        axios.get(`${API}/health`),
        axios.get(`${API}/agent-mail/config`),
        axios.get(`${API}/agent-mail/letters?limit=100`),
        axios.get(`${API}/outlook/status`),
        axios.get(`${API}/bud/assets?limit=50`),
        axios.get(`${API}/briefing/latest`),
        axios.get(`${API}/briefing/status`),
      ]);
      setHealth(h.data);
      setConfig(c.data);
      setLetters(l.data.letters || []);
      setOutlook(o.data);
      setAssets(a.data.assets || []);
      setBriefing(bL.data.empty ? null : bL.data);
      setBriefingStatus(bS.data);
      if (!baseUrlInput && c.data.bud_base_url) setBaseUrlInput(c.data.bud_base_url);
    } catch (e) {
      console.error("refresh failed", e);
      showToast("backend unreachable", "err");
    }
  }, [baseUrlInput]);

  const loadInbox = useCallback(async () => {
    if (!outlook?.connected) return;
    setOutlookLoading(true);
    try {
      const r = await axios.get(`${API}/outlook/inbox?limit=15`);
      setOutlookMail(r.data.messages || []);
    } catch (e) {
      showToast(e.response?.data?.detail || "inbox fetch failed", "err");
    } finally {
      setOutlookLoading(false);
    }
  }, [outlook?.connected]);

  useEffect(() => {
    if (outlook?.connected) loadInbox();
    else setOutlookMail([]);
  }, [outlook?.connected, loadInbox]);

  // Handle ?outlook=connected|error redirect from OAuth callback
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const ol = sp.get("outlook");
    if (ol === "connected") {
      showToast("outlook connected");
      window.history.replaceState({}, "", window.location.pathname);
      refresh();
    } else if (ol === "error") {
      showToast(`outlook: ${sp.get("msg") || "error"}`, "err");
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []); // eslint-disable-line

  useEffect(() => {
    // Auto-fill base URL from frontend env if config doesn't have one yet
    if (!baseUrlInput && BACKEND_URL) setBaseUrlInput(BACKEND_URL);
    refresh();
    const t = setInterval(refresh, 8000);
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

  const connectOutlook = () => {
    window.location.href = `${API}/outlook/oauth/start`;
  };

  const disconnectOutlook = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/outlook/disconnect`);
      showToast("outlook disconnected");
      await refresh();
    } catch (e) {
      showToast("disconnect failed", "err");
    } finally {
      setBusy(false);
    }
  };

  const submitReply = async () => {
    if (!replyFor || !replyBody.trim()) {
      showToast("body required", "err");
      return;
    }
    setBusy(true);
    try {
      const dr = await axios.post(`${API}/outlook/draft`, {
        message_id: replyFor.id,
        body: replyBody,
      });
      const draftId = dr.data.draft_id;
      await axios.post(`${API}/outlook/send/${encodeURIComponent(draftId)}`);
      showToast("reply sent");
      setReplyFor(null);
      setReplyBody("");
      await loadInbox();
    } catch (e) {
      showToast(e.response?.data?.detail || "reply failed", "err");
    } finally {
      setBusy(false);
    }
  };

  const saveDraftOnly = async () => {
    if (!replyFor || !replyBody.trim()) {
      showToast("body required", "err");
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/outlook/draft`, {
        message_id: replyFor.id,
        body: replyBody,
      });
      showToast("draft saved in Outlook");
      setReplyFor(null);
      setReplyBody("");
    } catch (e) {
      showToast(e.response?.data?.detail || "draft failed", "err");
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

  const copyAsset = async (asset) => {
    try {
      await navigator.clipboard.writeText(asset.content);
      setCopiedAssetId(asset.id);
      showToast("copied to clipboard");
      setTimeout(() => setCopiedAssetId(null), 1800);
    } catch (e) {
      showToast("copy failed — long-press the block", "err");
    }
  };

  const loadAssetIntoCompose = (asset) => {
    const content = asset.content || "";
    // Try to parse "To: ...\nSubject: ...\n\nbody"
    let to = "";
    let cc = "";
    let subject = "";
    let body = content;
    const lines = content.split("\n");
    let headerLines = 0;
    for (let i = 0; i < Math.min(lines.length, 6); i++) {
      const m = lines[i].match(/^(To|Cc|Subject):\s*(.+)$/i);
      if (!m) break;
      const key = m[1].toLowerCase();
      const val = m[2].trim();
      if (key === "to") to = val;
      else if (key === "cc") cc = val;
      else if (key === "subject") subject = val;
      headerLines = i + 1;
    }
    if (headerLines > 0) {
      // Drop header lines + leading blank line
      let rest = lines.slice(headerLines);
      while (rest.length && rest[0].trim() === "") rest.shift();
      body = rest.join("\n");
    } else if (asset.kind === "email" && asset.title) {
      // Fallback: use title as subject prefix
      subject = asset.title;
    }
    if (to) setSendTo(to);
    if (cc) setSendCc(cc);
    if (subject) setSendSubject(subject);
    setSendBody(body);
    setSendOpen(true);
    showToast(`loaded "${asset.title}"`);
  };

  const archiveAsset = async (asset) => {
    try {
      await axios.post(`${API}/bud/assets/${asset.id}/archive`);
      await refresh();
    } catch (e) {
      showToast("archive failed", "err");
    }
  };

  const runBriefing = async ({ email = true } = {}) => {
    setBriefingBusy(true);
    try {
      const endpoint = email ? "/briefing/run" : "/briefing/preview";
      const r = await axios.post(`${API}${endpoint}`, email ? { email: true } : {});
      showToast(
        email && r.data.delivery?.sent
          ? `briefing sent to ${r.data.delivery.recipient}`
          : "briefing generated"
      );
      await refresh();
    } catch (e) {
      showToast(e.response?.data?.detail || "briefing failed", "err");
    } finally {
      setBriefingBusy(false);
    }
  };

  const sendOutlookEmail = async ({ asDraft = false } = {}) => {
    const toList = sendTo.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
    const ccList = sendCc.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
    if (toList.length === 0) {
      showToast("To: required", "err");
      return;
    }
    if (!sendSubject.trim()) {
      showToast("Subject required", "err");
      return;
    }
    if (!sendBody.trim()) {
      showToast("Body required", "err");
      return;
    }
    setBusy(true);
    try {
      const endpoint = asDraft ? "/outlook/draft-new" : "/outlook/send-new";
      await axios.post(`${API}${endpoint}`, {
        to: toList,
        cc: ccList.length ? ccList : null,
        subject: sendSubject,
        body: sendBody,
        content_type: "Text",
      });
      showToast(asDraft ? "draft saved in Outlook" : `sent to ${toList.join(", ")}`);
      setSendTo("");
      setSendCc("");
      setSendSubject("");
      setSendBody("");
      setSendOpen(false);
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
          <VoiceRealtimePanel showToast={showToast} />
          <Section
            title="Daily Briefing"
            kicker={
              briefingStatus
                ? `GPT-5.2 · NEXT FIRE ${briefingStatus.next_run ? new Date(briefingStatus.next_run).toLocaleString() : "—"}`
                : "GPT-5.2 · LOADING"
            }
            right={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => runBriefing({ email: false })}
                  disabled={briefingBusy}
                  className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                  data-testid="briefing-preview-btn"
                  title="Generate without emailing"
                >
                  <RefreshCw size={14} className={briefingBusy ? "animate-spin" : ""} />
                  preview
                </button>
                <button
                  onClick={() => runBriefing({ email: true })}
                  disabled={briefingBusy || !outlook?.connected}
                  className="bud-btn-primary px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                  data-testid="briefing-run-btn"
                  title="Generate AND email to Doc"
                >
                  <Play size={14} /> run + send
                </button>
              </div>
            }
          >
            {!briefing ? (
              <div className="bud-card-inset p-6 text-xs text-[var(--bud-muted)] text-center" data-testid="briefing-empty">
                <Sunrise size={22} className="mx-auto mb-2 text-[var(--bud-amber)]" />
                no briefing yet. hit <strong className="text-[var(--bud-amber)]">preview</strong> to generate one now,
                or wait for the 7 AM CT cron.
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-[10px] text-[var(--bud-muted)]">
                  <span className="inline-flex items-center gap-1.5">
                    <Clock size={11} /> generated {new Date(briefing.created_at).toLocaleString()}
                  </span>
                  <span>
                    {briefing.sent ? (
                      <span style={{ color: "var(--bud-green)" }}>· emailed to inbox</span>
                    ) : (
                      <span>· preview only (not emailed)</span>
                    )}
                  </span>
                </div>
                <pre
                  className="text-xs text-[var(--bud-text)] whitespace-pre-wrap break-words leading-relaxed bud-card-inset p-4 max-h-[520px] overflow-auto"
                  data-testid="briefing-body"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
{briefing.body_md}
                </pre>
                <div className="flex items-center justify-end gap-2">
                  <button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(briefing.body_md);
                        showToast("briefing copied");
                      } catch (e) {
                        showToast("copy failed", "err");
                      }
                    }}
                    className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                    data-testid="briefing-copy-btn"
                  >
                    <Clipboard size={14} /> copy
                  </button>
                </div>
              </div>
            )}
          </Section>


          <Section
            title="Quick Assets"
            kicker={`BUD → DOC · ${assets.length} ready`}
            right={
              <span className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)]">
                one-tap copy
              </span>
            }
          >
            {assets.length === 0 ? (
              <div className="text-xs text-[var(--bud-muted)] py-6 text-center" data-testid="assets-empty">
                nothing queued. when Bud generates content for you (email body, snippet,
                address, login info, talking points) it lands here with a copy button.
              </div>
            ) : (
              <div className="space-y-3 max-h-[520px] overflow-auto pr-1">
                {assets.map((a) => {
                  const lines = (a.content || "").split("\n").length;
                  const preview = (a.content || "").slice(0, 280);
                  const truncated = (a.content || "").length > 280;
                  return (
                    <div
                      key={a.id}
                      className="bud-card-inset p-4"
                      data-testid={`asset-${a.id}`}
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span
                              className="text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded"
                              style={{
                                background: "rgba(245,158,11,0.12)",
                                color: "var(--bud-amber)",
                                border: "1px solid rgba(245,158,11,0.3)",
                              }}
                            >
                              {a.kind}
                            </span>
                            <span className="text-[10px] text-[var(--bud-muted)]">
                              {lines} {lines === 1 ? "line" : "lines"} ·{" "}
                              {new Date(a.created_at).toLocaleString()}
                            </span>
                          </div>
                          <div className="text-sm text-[var(--bud-text)] font-semibold truncate">
                            {a.title}
                          </div>
                          {a.note && (
                            <div className="text-[11px] text-[var(--bud-muted)] mt-1 leading-relaxed">
                              {a.note}
                            </div>
                          )}
                        </div>
                      </div>

                      <pre
                        className="text-xs text-[var(--bud-text)] whitespace-pre-wrap break-words leading-relaxed bg-[#0a0a0b] border border-[var(--bud-line)] rounded p-3 max-h-40 overflow-auto"
                        data-testid={`asset-content-${a.id}`}
                      >
{preview}{truncated ? "…" : ""}
                      </pre>

                      <div className="flex items-center justify-between gap-2 mt-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            onClick={() => copyAsset(a)}
                            className="bud-btn-primary px-4 py-2 rounded text-sm inline-flex items-center gap-2"
                            data-testid={`asset-copy-${a.id}`}
                          >
                            {copiedAssetId === a.id ? (
                              <><Check size={14}/> copied</>
                            ) : (
                              <><Clipboard size={14}/> COPY ALL</>
                            )}
                          </button>
                          {outlook?.connected && (
                            <button
                              onClick={() => {
                                loadAssetIntoCompose(a);
                                document
                                  .querySelector('[data-testid="outlook-compose-panel"]')
                                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
                              }}
                              className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                              data-testid={`asset-use-${a.id}`}
                              style={{ borderColor: "var(--bud-amber)", color: "var(--bud-amber)" }}
                            >
                              <Send size={14}/> USE IN COMPOSE
                            </button>
                          )}
                          {a.related_url && (
                            <a
                              href={a.related_url}
                              target="_blank"
                              rel="noreferrer"
                              className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                              data-testid={`asset-open-${a.id}`}
                            >
                              <ExternalLink size={14}/> open
                            </a>
                          )}
                        </div>
                        <button
                          onClick={() => archiveAsset(a)}
                          className="text-[10px] tracking-wider uppercase text-[var(--bud-muted)] hover:text-[var(--bud-text)] inline-flex items-center gap-1"
                          data-testid={`asset-archive-${a.id}`}
                        >
                          <Archive size={11}/> archive
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>


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
            title="Outlook"
            kicker={`MICROSOFT GRAPH · ${outlook?.connected ? outlook.email : "not connected"}`}
            right={
              outlook?.connected ? (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSendOpen((v) => !v)}
                    className="bud-btn-primary px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                    data-testid="outlook-compose-btn"
                  >
                    <Send size={14} /> {sendOpen ? "close" : "new email"}
                  </button>
                  <button
                    onClick={loadInbox}
                    disabled={outlookLoading}
                    className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                    data-testid="outlook-refresh-btn"
                  >
                    <RefreshCw size={14} className={outlookLoading ? "animate-spin" : ""} />
                    refresh
                  </button>
                  <button
                    onClick={disconnectOutlook}
                    disabled={busy}
                    className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
                    data-testid="outlook-disconnect-btn"
                  >
                    <Link2Off size={14} /> disconnect
                  </button>
                </div>
              ) : (
                <button
                  onClick={connectOutlook}
                  className="bud-btn-primary px-4 py-2 rounded text-sm inline-flex items-center gap-2"
                  data-testid="outlook-connect-btn"
                >
                  <Link2 size={14} /> Connect Outlook
                </button>
              )
            }
          >
            {!outlook?.connected ? (
              <div className="bud-card-inset p-4 text-xs text-[var(--bud-muted)] leading-relaxed">
                <div className="text-[var(--bud-text)] mb-2 font-semibold">
                  Microsoft Graph not connected.
                </div>
                Hit <strong className="text-[var(--bud-amber)]">Connect Outlook</strong> →
                sign in as <code>doc@drunderhood.com</code> → consent to the 5 scopes
                (<code>Mail.Read</code>, <code>Mail.Send</code>, <code>Mail.ReadWrite</code>,
                <code>User.Read</code>, <code>offline_access</code>). You'll land back here.
              </div>
            ) : (
              <>
                {sendOpen && (
                  <div className="bud-card-inset p-4 mb-4 space-y-3" data-testid="outlook-compose-panel">
                    {assets.length > 0 && (
                      <div
                        className="rounded p-3 mb-1"
                        style={{
                          background: "rgba(245,158,11,0.06)",
                          border: "1px dashed rgba(245,158,11,0.35)",
                        }}
                        data-testid="compose-asset-picker"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="text-[10px] tracking-[0.25em] text-[var(--bud-amber)]">
                            BUD WROTE THESE FOR YOU — TAP TO LOAD
                          </div>
                          <div className="text-[10px] text-[var(--bud-muted)]">
                            {assets.length} ready
                          </div>
                        </div>
                        <div className="space-y-1.5 max-h-44 overflow-auto pr-1">
                          {assets.slice(0, 8).map((a) => (
                            <button
                              key={a.id}
                              onClick={() => loadAssetIntoCompose(a)}
                              className="w-full text-left bud-card-inset px-3 py-2 hover:border-[var(--bud-amber)] transition-colors"
                              data-testid={`compose-asset-use-${a.id}`}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="min-w-0 flex-1">
                                  <div className="text-xs text-[var(--bud-text)] font-semibold truncate">
                                    {a.title}
                                  </div>
                                  <div className="text-[10px] text-[var(--bud-muted)] truncate">
                                    {(a.content || "").slice(0, 90)}…
                                  </div>
                                </div>
                                <span
                                  className="text-[10px] tracking-widest uppercase px-2 py-0.5 rounded"
                                  style={{
                                    background: "var(--bud-amber)",
                                    color: "#0a0a0b",
                                    fontWeight: 600,
                                  }}
                                >
                                  use →
                                </span>
                              </div>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">TO</div>
                        <input
                          type="text"
                          placeholder="recipient@example.com (comma or space separated)"
                          value={sendTo}
                          onChange={(e) => setSendTo(e.target.value)}
                          className="bud-input w-full px-3 py-2 rounded text-xs"
                          data-testid="outlook-to-input"
                        />
                      </div>
                      <div>
                        <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">CC (optional)</div>
                        <input
                          type="text"
                          placeholder="cc@example.com"
                          value={sendCc}
                          onChange={(e) => setSendCc(e.target.value)}
                          className="bud-input w-full px-3 py-2 rounded text-xs"
                          data-testid="outlook-cc-input"
                        />
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">SUBJECT</div>
                      <input
                        type="text"
                        placeholder="subject line"
                        value={sendSubject}
                        onChange={(e) => setSendSubject(e.target.value)}
                        className="bud-input w-full px-3 py-2 rounded text-sm"
                        data-testid="outlook-subject-input"
                      />
                    </div>
                    <div>
                      <div className="text-[10px] tracking-[0.25em] text-[var(--bud-muted)] mb-1.5">BODY</div>
                      <textarea
                        placeholder="write your email. plain text. Doc's voice — direct, no fluff."
                        value={sendBody}
                        onChange={(e) => setSendBody(e.target.value)}
                        rows={10}
                        className="bud-input w-full px-3 py-2 rounded text-sm leading-relaxed"
                        data-testid="outlook-body-input"
                      />
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[10px] text-[var(--bud-muted)]">
                        sends as <code>{outlook.email}</code>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => sendOutlookEmail({ asDraft: true })}
                          disabled={busy}
                          className="bud-btn-ghost px-3 py-2 rounded text-sm"
                          data-testid="outlook-save-draft-btn"
                        >
                          save as draft
                        </button>
                        <button
                          onClick={() => sendOutlookEmail({ asDraft: false })}
                          disabled={busy}
                          className="bud-btn-primary px-4 py-2 rounded text-sm inline-flex items-center gap-2"
                          data-testid="outlook-send-now-btn"
                        >
                          <Send size={14} /> SEND NOW
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                {outlookLoading && outlookMail.length === 0 ? (
                  <div className="text-xs text-[var(--bud-muted)] py-6 text-center">loading inbox…</div>
                ) : outlookMail.length === 0 ? (
                  <div className="text-xs text-[var(--bud-muted)] py-6 text-center">
                    inbox empty — or no messages in the last batch.
                  </div>
                ) : (
              <div className="space-y-2 max-h-[480px] overflow-auto pr-1">
                {outlookMail.map((m) => (
                  <div
                    key={m.id}
                    className="bud-card-inset p-3 hover:border-[var(--bud-amber)] transition-colors"
                    style={{ borderColor: m.is_read ? undefined : "rgba(245,158,11,0.35)" }}
                    data-testid={`outlook-msg-${m.id}`}
                  >
                    <div className="flex items-start justify-between gap-3 mb-1">
                      <div className="flex items-center gap-2 min-w-0">
                        {!m.is_read && (
                          <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: "var(--bud-amber)" }}
                          />
                        )}
                        <span className="text-xs text-[var(--bud-text)] font-semibold truncate">
                          {m.from_name || m.from_email || "—"}
                        </span>
                        {m.has_attachments && <Paperclip size={11} className="text-[var(--bud-muted)]" />}
                      </div>
                      <span className="text-[10px] text-[var(--bud-muted)] whitespace-nowrap">
                        {m.received_at ? new Date(m.received_at).toLocaleString() : ""}
                      </span>
                    </div>
                    <div className="text-xs text-[var(--bud-text)] mb-1 truncate">
                      {m.subject}
                    </div>
                    <div className="text-[11px] text-[var(--bud-muted)] line-clamp-2 leading-relaxed">
                      {m.preview}
                    </div>
                    <div className="flex items-center gap-3 mt-2">
                      <button
                        onClick={() => {
                          setReplyFor(m);
                          setReplyBody("");
                        }}
                        className="text-[10px] tracking-wider uppercase text-[var(--bud-amber)] hover:text-[#fbbf24]"
                        data-testid={`outlook-reply-${m.id}`}
                      >
                        draft reply
                      </button>
                      {m.web_link && (
                        <a
                          href={m.web_link}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[10px] tracking-wider uppercase text-[var(--bud-muted)] hover:text-[var(--bud-text)] inline-flex items-center gap-1"
                        >
                          open in outlook <ExternalLink size={10} />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
              </>
            )}
          </Section>


          <Section
            title="Mailroom"
            kicker={(() => {
              const unread = letters.filter((l) => l.direction === "inbound" && !l.read).length;
              const ogRound = Math.max(0, ...letters.filter((l) => l.from_agent === "og" || l.to_agent === "og").map((l) => l.round || 0));
              const nineRound = Math.max(0, ...letters.filter((l) => l.from_agent === "nine" || l.to_agent === "nine").map((l) => l.round || 0));
              return `LETTERS · ${letters.length} · OG R${ogRound} · 9 R${nineRound}${unread ? ` · ${unread} UNREAD` : ""}`;
            })()}
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

      {replyFor && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.7)" }}
          onClick={(e) => e.target === e.currentTarget && setReplyFor(null)}
          data-testid="reply-modal"
        >
          <div className="bud-card max-w-2xl w-full p-6 fade-in">
            <div className="flex items-start justify-between mb-3">
              <div className="min-w-0">
                <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)] mb-1">
                  DRAFT REPLY TO
                </div>
                <div className="text-sm text-[var(--bud-text)] font-semibold truncate">
                  {replyFor.from_name || replyFor.from_email}
                </div>
                <div className="text-xs text-[var(--bud-muted)] truncate">
                  Re: {replyFor.subject}
                </div>
              </div>
              <button
                onClick={() => setReplyFor(null)}
                className="bud-btn-ghost px-2 py-1 rounded text-xs"
                data-testid="reply-close-btn"
              >
                close
              </button>
            </div>
            <div className="bud-card-inset p-3 mb-3 text-[11px] text-[var(--bud-muted)] max-h-32 overflow-auto leading-relaxed">
              {replyFor.preview}
            </div>
            <textarea
              value={replyBody}
              onChange={(e) => setReplyBody(e.target.value)}
              rows={10}
              placeholder="surgical reply. plain text. Doc's voice — no fluff, no upsell."
              className="bud-input w-full px-3 py-2 rounded text-sm leading-relaxed mb-3"
              data-testid="reply-body-input"
              autoFocus
            />
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={saveDraftOnly}
                disabled={busy}
                className="bud-btn-ghost px-3 py-2 rounded text-sm"
                data-testid="reply-save-draft-btn"
              >
                save draft
              </button>
              <button
                onClick={submitReply}
                disabled={busy}
                className="bud-btn-primary px-4 py-2 rounded text-sm inline-flex items-center gap-2"
                data-testid="reply-send-btn"
              >
                <Send size={14} /> send
              </button>
            </div>
          </div>
        </div>
      )}

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
