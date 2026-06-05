import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { Phone, PhoneOff, Mic, MicOff, Square, Loader2, Volume2, VolumeX } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime/calls";

export default function VoiceRealtimePanel({ showToast }) {
  const [state, setState] = useState("idle"); // idle | connecting | connected | hanging-up
  const [sessionId, setSessionId] = useState(null);
  const [model, setModel] = useState(null);
  const [micMuted, setMicMuted] = useState(false);
  const [speakerMuted, setSpeakerMuted] = useState(false);
  const [transcript, setTranscript] = useState([]); // {role, text, partial?}
  const [interruptable, setInterruptable] = useState(false);

  const pcRef = useRef(null);
  const dcRef = useRef(null);
  const audioElRef = useRef(null);
  const localStreamRef = useRef(null);
  const liveAssistantTextRef = useRef("");
  const liveUserTextRef = useRef("");

  const cleanup = useCallback(() => {
    try { dcRef.current?.close(); } catch (e) {}
    try { pcRef.current?.close(); } catch (e) {}
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((t) => t.stop());
      localStreamRef.current = null;
    }
    if (audioElRef.current) {
      try {
        audioElRef.current.srcObject = null;
      } catch (e) {}
    }
    dcRef.current = null;
    pcRef.current = null;
    setSessionId(null);
    setState("idle");
    setInterruptable(false);
  }, []);

  const handleServerEvent = useCallback((ev) => {
    // Reference: OpenAI Realtime events
    if (!ev?.type) return;
    if (ev.type.startsWith("response.")) setInterruptable(true);
    if (ev.type === "response.done" || ev.type === "response.cancelled") {
      setInterruptable(false);
      if (liveAssistantTextRef.current.trim()) {
        // commit
        setTranscript((prev) => [
          ...prev,
          { id: `a-${Date.now()}`, role: "assistant", text: liveAssistantTextRef.current.trim() },
        ]);
        liveAssistantTextRef.current = "";
      }
    }
    // Streamed assistant audio transcript deltas
    if (ev.type === "response.output_audio_transcript.delta" || ev.type === "response.audio_transcript.delta") {
      const delta = ev.delta || "";
      liveAssistantTextRef.current += delta;
      setTranscript((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant" && last.partial) {
          last.text = liveAssistantTextRef.current;
        } else {
          next.push({ id: `a-live`, role: "assistant", text: liveAssistantTextRef.current, partial: true });
        }
        return next.filter((t) => !(t.partial && t.text === ""));
      });
    }
    // User transcription (input audio)
    if (ev.type === "conversation.item.input_audio_transcription.completed") {
      const txt = ev.transcript || "";
      if (txt.trim()) {
        setTranscript((prev) => [
          ...prev.filter((t) => !(t.partial && t.role === "user")),
          { id: `u-${Date.now()}`, role: "user", text: txt.trim() },
        ]);
      }
    }
    if (ev.type === "input_audio_buffer.speech_started") {
      setInterruptable(true);
    }
    if (ev.type === "error") {
      console.error("Realtime error:", ev);
      showToast?.(`voice error: ${ev.error?.message || "unknown"}`, "err");
    }
  }, [showToast]);

  const startCall = async () => {
    if (state !== "idle") return;
    setState("connecting");
    setTranscript([]);
    try {
      // 1. Mint ephemeral key via Bud → 9
      const mintResp = await axios.post(`${API}/voice-rt/mint`, {
        voice: "ash",
        eagerness: "medium",
      });
      const { client_secret, session_id, model: gotModel } = mintResp.data;
      const ephemeralKey =
        typeof client_secret === "string" ? client_secret : client_secret?.value;
      if (!ephemeralKey) throw new Error("no client_secret returned");
      setSessionId(session_id);
      setModel(gotModel || "gpt-realtime");

      // 2. Build peer connection
      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      // 3. Remote audio playback
      pc.ontrack = (e) => {
        if (audioElRef.current) {
          audioElRef.current.srcObject = e.streams[0];
          audioElRef.current.play().catch(() => {});
        }
      };

      // 4. Local mic
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      localStreamRef.current = stream;
      stream.getTracks().forEach((t) => pc.addTrack(t, stream));

      // 5. Data channel for events
      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;
      dc.addEventListener("open", () => {
        // Enable input transcription for user turns
        try {
          dc.send(JSON.stringify({
            type: "session.update",
            session: {
              input_audio_transcription: { model: "whisper-1" },
            },
          }));
        } catch (e) {}
      });
      dc.addEventListener("message", (e) => {
        try { handleServerEvent(JSON.parse(e.data)); } catch (err) {}
      });

      // 6. SDP exchange with OpenAI Realtime
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const sdpResp = await fetch(`${OPENAI_REALTIME_URL}?model=${gotModel || "gpt-realtime"}`, {
        method: "POST",
        body: offer.sdp,
        headers: {
          Authorization: `Bearer ${ephemeralKey}`,
          "Content-Type": "application/sdp",
        },
      });
      if (!sdpResp.ok) {
        throw new Error(`SDP exchange failed: ${sdpResp.status} ${await sdpResp.text()}`);
      }
      const answerSdp = await sdpResp.text();
      await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

      setState("connected");
      showToast?.("voice connected — just talk");
    } catch (e) {
      console.error("call setup failed", e);
      showToast?.(e.message || "call setup failed", "err");
      cleanup();
    }
  };

  const hangUp = () => {
    setState("hanging-up");
    cleanup();
    showToast?.("voice call ended");
  };

  const shutUp = () => {
    if (!dcRef.current || dcRef.current.readyState !== "open") return;
    try {
      dcRef.current.send(JSON.stringify({ type: "response.cancel" }));
      setInterruptable(false);
    } catch (e) {}
  };

  const toggleMic = () => {
    if (!localStreamRef.current) return;
    const next = !micMuted;
    localStreamRef.current.getAudioTracks().forEach((t) => (t.enabled = !next));
    setMicMuted(next);
  };

  const toggleSpeaker = () => {
    const next = !speakerMuted;
    if (audioElRef.current) audioElRef.current.muted = next;
    setSpeakerMuted(next);
  };

  useEffect(() => () => cleanup(), [cleanup]);

  return (
    <section className="bud-card p-5 fade-in" data-testid="section-voice-rt">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)] mb-1">
            {model ? `${model.toUpperCase()} · VIA 9` : "OPENAI REALTIME · VIA 9"}
          </div>
          <h2 className="bud-display text-xl text-[var(--bud-text)]">Talk to Bud</h2>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] tracking-widest uppercase px-2 py-1 rounded"
            style={{
              background:
                state === "connected" ? "rgba(132,204,22,0.1)" :
                state === "connecting" ? "rgba(245,158,11,0.1)" :
                "transparent",
              color:
                state === "connected" ? "var(--bud-green)" :
                state === "connecting" ? "var(--bud-amber)" :
                "var(--bud-muted)",
              border: `1px solid ${
                state === "connected" ? "rgba(132,204,22,0.3)" :
                state === "connecting" ? "rgba(245,158,11,0.3)" :
                "var(--bud-line)"
              }`,
            }}
            data-testid="voice-rt-state"
          >
            {state}
          </span>
        </div>
      </div>

      {transcript.length > 0 && (
        <div className="space-y-2 max-h-[360px] overflow-auto pr-1 mb-4" data-testid="voice-rt-transcript">
          {[...transcript].reverse().map((t) => (
            <div
              key={t.id}
              className="bud-card-inset p-3"
              style={
                t.role === "assistant"
                  ? { background: "rgba(245,158,11,0.04)", borderColor: "rgba(245,158,11,0.25)" }
                  : {}
              }
            >
              <div className="text-[10px] tracking-widest mb-1" style={{
                color: t.role === "assistant" ? "var(--bud-amber)" : "var(--bud-muted)"
              }}>
                {t.role === "assistant" ? "BUD" : "DOC"}{t.partial ? " · live" : ""}
              </div>
              <div className="text-sm text-[var(--bud-text)] whitespace-pre-wrap leading-relaxed">
                {t.text}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col items-center gap-4 py-4">
        {state === "idle" && (
          <button
            onClick={startCall}
            className="w-32 h-32 rounded-full flex items-center justify-center"
            data-testid="voice-rt-connect-btn"
            style={{
              background: "linear-gradient(135deg, var(--bud-amber), var(--bud-rust))",
              boxShadow: "0 0 32px var(--bud-amber-glow)",
              border: "none",
              cursor: "pointer",
            }}
          >
            <Phone size={48} color="#0a0a0b" strokeWidth={2.5} />
          </button>
        )}
        {state === "connecting" && (
          <div
            className="w-32 h-32 rounded-full flex items-center justify-center"
            style={{ background: "var(--bud-panel-2)", border: "2px solid var(--bud-amber)" }}
          >
            <Loader2 size={48} color="var(--bud-amber)" className="animate-spin" />
          </div>
        )}
        {state === "connected" && (
          <div className="flex items-center gap-4">
            <button
              onClick={toggleMic}
              className="w-16 h-16 rounded-full flex items-center justify-center"
              data-testid="voice-rt-mic-btn"
              style={{
                background: micMuted ? "var(--bud-panel-2)" : "linear-gradient(135deg, #84cc16, #65a30d)",
                border: micMuted ? "1px solid var(--bud-line)" : "none",
                cursor: "pointer",
              }}
              title={micMuted ? "mic muted — tap to unmute" : "mic live — tap to mute"}
            >
              {micMuted ? <MicOff size={24} color="var(--bud-muted)" /> : <Mic size={26} color="#0a0a0b" strokeWidth={2.5} />}
            </button>

            <button
              onClick={interruptable ? shutUp : undefined}
              disabled={!interruptable}
              className="w-20 h-20 rounded-full flex items-center justify-center"
              data-testid="voice-rt-shutup-btn"
              style={{
                background: interruptable ? "linear-gradient(135deg, #6366f1, #4338ca)" : "var(--bud-panel-2)",
                border: interruptable ? "none" : "1px solid var(--bud-line)",
                cursor: interruptable ? "pointer" : "default",
                opacity: interruptable ? 1 : 0.4,
                boxShadow: interruptable ? "0 0 24px rgba(99,102,241,0.45)" : "none",
              }}
              title="shut up — interrupt Bud mid-sentence"
            >
              <Square size={28} color={interruptable ? "#fff" : "var(--bud-muted)"} fill={interruptable ? "#fff" : "transparent"} />
            </button>

            <button
              onClick={hangUp}
              className="w-16 h-16 rounded-full flex items-center justify-center"
              data-testid="voice-rt-hangup-btn"
              style={{
                background: "linear-gradient(135deg, #ef4444, #c2410c)",
                border: "none",
                cursor: "pointer",
              }}
              title="end call"
            >
              <PhoneOff size={24} color="#fff" strokeWidth={2.5} />
            </button>

            <button
              onClick={toggleSpeaker}
              className="w-12 h-12 rounded-full flex items-center justify-center"
              data-testid="voice-rt-speaker-btn"
              style={{
                background: "transparent",
                border: "1px solid var(--bud-line)",
                cursor: "pointer",
              }}
              title={speakerMuted ? "speaker muted" : "speaker on"}
            >
              {speakerMuted ? <VolumeX size={18} color="var(--bud-muted)" /> : <Volume2 size={18} color="var(--bud-text)" />}
            </button>
          </div>
        )}

        <div className="text-[10px] tracking-[0.3em] text-[var(--bud-muted)] text-center">
          {state === "idle"      ? "TAP TO CALL BUD" :
           state === "connecting" ? "CONNECTING…"     :
           state === "connected"  ? (interruptable ? "TAP THE BLUE STOP TO CUT BUD OFF" : "JUST TALK — HE'S LISTENING") :
                                    "ENDING CALL…"}
        </div>
        {sessionId && state === "connected" && (
          <div className="text-[10px] text-[var(--bud-muted)] opacity-60">
            session: {sessionId.slice(0, 8)}…
          </div>
        )}
      </div>

      <audio ref={audioElRef} autoPlay playsInline className="hidden" />
    </section>
  );
}
