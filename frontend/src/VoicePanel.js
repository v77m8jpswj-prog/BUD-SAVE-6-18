import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { Mic, MicOff, Volume2, Trash2, Loader2, Send, RefreshCw } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const SESSION_KEY = "bud_voice_session_id";

function ensureSessionId() {
  let s = localStorage.getItem(SESSION_KEY);
  if (!s) {
    s = (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(SESSION_KEY, s);
  }
  return s;
}

function b64ToBlob(b64, mime = "audio/mpeg") {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

export default function VoicePanel({ showToast }) {
  const [sessionId] = useState(() => ensureSessionId());
  const [history, setHistory] = useState([]);
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [muted, setMuted] = useState(false);
  const [typed, setTyped] = useState("");
  const [config, setConfig] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const audioRef = useRef(null);
  const lastAudioUrlRef = useRef(null);

  const loadHistory = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/voice/history?session_id=${sessionId}&limit=50`);
      setHistory(r.data.turns || []);
    } catch (e) {
      console.error("history load failed", e);
    }
  }, [sessionId]);

  useEffect(() => {
    axios.get(`${API}/voice/config`).then((r) => setConfig(r.data)).catch(() => {});
    loadHistory();
  }, [loadHistory]);

  const playAudio = useCallback((b64) => {
    if (!b64 || muted) return;
    if (lastAudioUrlRef.current) URL.revokeObjectURL(lastAudioUrlRef.current);
    const blob = b64ToBlob(b64, "audio/mpeg");
    const url = URL.createObjectURL(blob);
    lastAudioUrlRef.current = url;
    if (audioRef.current) {
      audioRef.current.src = url;
      audioRef.current.play().catch(() => {});
    }
  }, [muted]);

  const submitAudio = async (blob) => {
    setProcessing(true);
    try {
      const fd = new FormData();
      fd.append("audio", blob, "turn.webm");
      fd.append("session_id", sessionId);
      fd.append("speak", muted ? "false" : "true");
      const r = await axios.post(`${API}/voice/turn`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 90000,
      });
      playAudio(r.data.audio_base64);
      await loadHistory();
    } catch (e) {
      showToast?.(e.response?.data?.detail || "voice turn failed", "err");
    } finally {
      setProcessing(false);
    }
  };

  const submitText = async () => {
    if (!typed.trim()) return;
    const text = typed.trim();
    setTyped("");
    setProcessing(true);
    try {
      const r = await axios.post(`${API}/voice/text-turn`, {
        text,
        session_id: sessionId,
        speak: !muted,
      });
      playAudio(r.data.audio_base64);
      await loadHistory();
    } catch (e) {
      showToast?.(e.response?.data?.detail || "voice turn failed", "err");
    } finally {
      setProcessing(false);
    }
  };

  const startRecording = async () => {
    if (recording || processing) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: mime || "audio/webm" });
        // Cleanup mic
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
        }
        if (blob.size > 800) {
          await submitAudio(blob);
        } else {
          showToast?.("too quiet — try again", "err");
        }
      };
      mr.start();
      setRecording(true);
    } catch (e) {
      showToast?.("mic blocked — allow microphone access in your browser", "err");
    }
  };

  const stopRecording = () => {
    if (!recording) return;
    try {
      mediaRecorderRef.current?.stop();
    } catch (e) {}
    setRecording(false);
  };

  const clearSession = async () => {
    if (!window.confirm("Wipe this voice conversation?")) return;
    try {
      await axios.delete(`${API}/voice/history?session_id=${sessionId}`);
      setHistory([]);
      showToast?.("voice memory wiped");
    } catch (e) {
      showToast?.("wipe failed", "err");
    }
  };

  const replay = (b64) => playAudio(b64);

  return (
    <section className="bud-card p-5 fade-in" data-testid="section-talk-to-bud">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)] mb-1">
            {config ? `${config.chat_model} · ${config.voice} voice · whisper-1` : "VOICE LOOP"}
          </div>
          <h2 className="bud-display text-xl text-[var(--bud-text)]">Talk to Bud</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMuted((v) => !v)}
            className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
            data-testid="voice-mute-btn"
            title={muted ? "voice OFF — Bud will reply in text only" : "voice ON — Bud speaks"}
          >
            <Volume2 size={14} className={muted ? "opacity-40" : ""} />
            {muted ? "muted" : "speaking"}
          </button>
          <button
            onClick={clearSession}
            className="bud-btn-ghost px-3 py-2 rounded text-sm inline-flex items-center gap-2"
            data-testid="voice-clear-btn"
            title="wipe this conversation"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="flex flex-col items-center gap-3 py-4">
        <button
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onMouseLeave={() => recording && stopRecording()}
          onTouchStart={(e) => { e.preventDefault(); startRecording(); }}
          onTouchEnd={(e) => { e.preventDefault(); stopRecording(); }}
          disabled={processing}
          data-testid="voice-ptt-btn"
          className="relative w-24 h-24 rounded-full flex items-center justify-center transition-all duration-150"
          style={{
            background: recording
              ? "linear-gradient(135deg, #ef4444, #c2410c)"
              : processing
              ? "var(--bud-panel-2)"
              : "linear-gradient(135deg, var(--bud-amber), var(--bud-rust))",
            boxShadow: recording
              ? "0 0 0 8px rgba(239,68,68,0.18), 0 0 32px rgba(239,68,68,0.4)"
              : "0 0 28px var(--bud-amber-glow)",
            transform: recording ? "scale(1.06)" : "scale(1)",
            cursor: processing ? "wait" : "pointer",
          }}
        >
          {processing ? (
            <Loader2 size={36} color="#0a0a0b" className="animate-spin" />
          ) : recording ? (
            <MicOff size={36} color="#0a0a0b" strokeWidth={2.5} />
          ) : (
            <Mic size={36} color="#0a0a0b" strokeWidth={2.5} />
          )}
        </button>
        <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)]">
          {processing ? "BUD IS THINKING…" : recording ? "HOLD & TALK · RELEASE TO SEND" : "HOLD TO TALK"}
        </div>
      </div>

      <div className="flex items-center gap-2 mt-2">
        <input
          type="text"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submitText()}
          placeholder="…or type if the shop is loud"
          className="bud-input flex-1 px-3 py-2 rounded text-sm"
          data-testid="voice-text-input"
          disabled={processing}
        />
        <button
          onClick={submitText}
          disabled={processing || !typed.trim()}
          className="bud-btn-primary px-4 py-2 rounded text-sm inline-flex items-center gap-2"
          data-testid="voice-text-send-btn"
        >
          <Send size={14} /> send
        </button>
      </div>

      {history.length > 0 && (
        <div className="mt-5 space-y-3 max-h-[420px] overflow-auto pr-1" data-testid="voice-history">
          {history.map((t) => (
            <div key={t.id} className="space-y-1.5 fade-in">
              <div className="bud-card-inset p-3" data-testid={`voice-user-${t.id}`}>
                <div className="text-[10px] tracking-widest text-[var(--bud-muted)] mb-1">
                  DOC {t.input_was_audio ? "· voice" : "· typed"} · {new Date(t.created_at).toLocaleTimeString()}
                </div>
                <div className="text-sm text-[var(--bud-text)]">{t.user_text}</div>
              </div>
              <div
                className="bud-card-inset p-3"
                style={{
                  background: "rgba(245,158,11,0.04)",
                  borderColor: "rgba(245,158,11,0.25)",
                }}
                data-testid={`voice-bud-${t.id}`}
              >
                <div className="text-[10px] tracking-widest text-[var(--bud-amber)] mb-1">BUD</div>
                <div className="text-sm text-[var(--bud-text)] leading-relaxed whitespace-pre-wrap">
                  {t.bud_text}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <audio ref={audioRef} className="hidden" data-testid="voice-audio" />
    </section>
  );
}
