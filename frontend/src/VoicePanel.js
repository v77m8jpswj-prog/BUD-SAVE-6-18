import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { Mic, MicOff, Volume2, Trash2, Loader2, Send, Square } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const SESSION_KEY = "bud_voice_session_id";

// Silence detection tuning
const SILENCE_THRESHOLD = 0.012; // RMS — anything below this is "silent"
const SILENCE_HANGOVER_MS = 1800; // stop after this much continuous silence
const MIN_SPEECH_MS = 350; // must have spoken at least this long
const MAX_RECORDING_MS = 60_000; // hard cap

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
  const [level, setLevel] = useState(0); // 0..1 live mic RMS for the meter
  const [hint, setHint] = useState("TAP TO TALK");

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const rafRef = useRef(null);
  const audioRef = useRef(null);
  const lastAudioUrlRef = useRef(null);

  // Speech-state refs (avoid stale closures from RAF)
  const startedAtRef = useRef(0);
  const lastVoiceAtRef = useRef(0);
  const hasVoicedRef = useRef(false);
  const maxStopTimeoutRef = useRef(null);
  const cancelledRef = useRef(false);

  const loadHistory = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/voice/history?session_id=${sessionId}&limit=50`);
      setHistory(r.data.turns || []);
    } catch (e) {
      // ignore
    }
  }, [sessionId]);

  useEffect(() => {
    axios.get(`${API}/voice/config`).then((r) => setConfig(r.data)).catch(() => {});
    loadHistory();
    return () => cleanupAudio();
    // eslint-disable-next-line
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

  const cleanupAudio = () => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (maxStopTimeoutRef.current) {
      clearTimeout(maxStopTimeoutRef.current);
      maxStopTimeoutRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close(); } catch (e) {}
      audioCtxRef.current = null;
    }
    analyserRef.current = null;
    setLevel(0);
  };

  const stopRecording = useCallback(({ cancel = false } = {}) => {
    cancelledRef.current = cancel;
    if (!recording) {
      cleanupAudio();
      return;
    }
    try { mediaRecorderRef.current?.stop(); } catch (e) {}
    setRecording(false);
  }, [recording]);

  const tickVAD = () => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const buf = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    setLevel(Math.min(1, rms * 10));

    const now = performance.now();
    if (rms > SILENCE_THRESHOLD) {
      lastVoiceAtRef.current = now;
      if (!hasVoicedRef.current && now - startedAtRef.current > 80) {
        hasVoicedRef.current = true;
        setHint("LISTENING…");
      }
    } else if (hasVoicedRef.current) {
      const silentFor = now - lastVoiceAtRef.current;
      const totalSpeech = lastVoiceAtRef.current - startedAtRef.current;
      if (silentFor > SILENCE_HANGOVER_MS && totalSpeech > MIN_SPEECH_MS) {
        // Auto-stop
        stopRecording();
        return;
      }
    }
    rafRef.current = requestAnimationFrame(tickVAD);
  };

  const startRecording = async () => {
    if (recording || processing) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;

      // VAD setup
      const AC = window.AudioContext || window.webkitAudioContext;
      const ctx = new AC();
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      src.connect(analyser);
      analyserRef.current = analyser;

      // Recorder
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      chunksRef.current = [];
      cancelledRef.current = false;
      hasVoicedRef.current = false;
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        const wasCancelled = cancelledRef.current;
        const voiced = hasVoicedRef.current;
        const blob = new Blob(chunksRef.current, { type: mime || "audio/webm" });
        cleanupAudio();
        setHint("TAP TO TALK");
        if (wasCancelled) return;
        if (!voiced || blob.size < 1500) {
          showToast?.("didn't catch anything — tap and try again", "err");
          return;
        }
        await submitAudio(blob);
      };
      mr.start();

      startedAtRef.current = performance.now();
      lastVoiceAtRef.current = startedAtRef.current;
      setRecording(true);
      setHint("WAITING FOR YOU…");
      rafRef.current = requestAnimationFrame(tickVAD);

      maxStopTimeoutRef.current = setTimeout(() => {
        if (recording) stopRecording();
      }, MAX_RECORDING_MS);
    } catch (e) {
      cleanupAudio();
      showToast?.("mic blocked — allow microphone access in your browser", "err");
    }
  };

  const handlePttClick = () => {
    if (processing) return;
    if (recording) stopRecording();
    else startRecording();
  };

  const cancelRecording = () => stopRecording({ cancel: true });

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

  const meterPct = Math.round(level * 100);

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
            title={muted ? "voice OFF — text replies only" : "voice ON — Bud speaks"}
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

      <div className="flex flex-col items-center gap-3 py-5">
        <div className="relative">
          {recording && (
            <div
              aria-hidden
              style={{
                position: "absolute",
                inset: -10 - meterPct * 0.18,
                borderRadius: "9999px",
                background:
                  "radial-gradient(circle, rgba(245,158,11,0.25) 0%, rgba(245,158,11,0) 70%)",
                pointerEvents: "none",
                transition: "inset 80ms ease-out",
              }}
            />
          )}
          <button
            onClick={handlePttClick}
            disabled={processing}
            data-testid="voice-ptt-btn"
            className="relative w-28 h-28 rounded-full flex items-center justify-center"
            style={{
              background: recording
                ? "linear-gradient(135deg, #ef4444, #c2410c)"
                : processing
                ? "var(--bud-panel-2)"
                : "linear-gradient(135deg, var(--bud-amber), var(--bud-rust))",
              boxShadow: recording
                ? `0 0 0 ${8 + meterPct * 0.2}px rgba(239,68,68,0.16), 0 0 40px rgba(239,68,68,0.5)`
                : "0 0 28px var(--bud-amber-glow)",
              transform: recording ? "scale(1.04)" : "scale(1)",
              cursor: processing ? "wait" : "pointer",
              transition: "box-shadow 80ms ease-out, transform 120ms ease",
              border: "none",
            }}
          >
            {processing ? (
              <Loader2 size={40} color="#0a0a0b" className="animate-spin" />
            ) : recording ? (
              <Square size={36} color="#0a0a0b" strokeWidth={2.8} fill="#0a0a0b" />
            ) : (
              <Mic size={40} color="#0a0a0b" strokeWidth={2.5} />
            )}
          </button>
        </div>

        <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)] h-3" data-testid="voice-hint">
          {processing ? "BUD IS THINKING…" : hint}
        </div>

        {recording && (
          <div className="flex items-center gap-2 text-[10px] tracking-widest text-[var(--bud-muted)]">
            <span>AUTO-STOPS ON SILENCE</span>
            <span>·</span>
            <button
              onClick={cancelRecording}
              className="hover:text-[var(--bud-red)] uppercase tracking-widest"
              data-testid="voice-cancel-btn"
            >
              cancel
            </button>
          </div>
        )}
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
