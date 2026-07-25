"use client";

import { useState } from "react";
import { api, type ChatResponse } from "@/lib/api";
import { CitationList } from "./CitationList";

type Turn = { question: string; response: ChatResponse | null; error?: string };

export function ChatWindow() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const q = draft.trim();
    if (!q || busy) return;
    setDraft("");
    setBusy(true);
    setTurns((t) => [...t, { question: q, response: null }]);
    try {
      const history = turns.map((t) => t.question).slice(-3);
      const response = await api.ask(q, history);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, response } : turn)));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "request failed";
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: msg } : turn)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      {turns.map((t, i) => (
        <div key={i} style={{ marginBottom: 28 }}>
          <p style={{ fontWeight: 500 }}>{t.question}</p>

          {t.error && <p style={{ color: "#a32d2d" }}>{t.error}</p>}
          {!t.response && !t.error && <p style={{ color: "#8b8a84" }}>Searching your documents…</p>}

          {t.response && (
            <>
              <p style={{ whiteSpace: "pre-wrap" }}>{t.response.answer}</p>

              {/* Grounding is surfaced, not hidden. Downgrading a confident wrong
                  answer to a flagged one is the whole value of verification. */}
              {t.response.grounded === false && (
                <p style={{ fontSize: 13, color: "#854f0b" }}>
                  Some statements could not be matched to the sources below.
                </p>
              )}

              <CitationList citations={t.response.citations} />
            </>
          )}
        </div>
      ))}

      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about your documents"
          style={{ flex: 1, padding: "10px 12px", borderRadius: 8, border: "1px solid #d5d3cb" }}
        />
        <button onClick={send} disabled={busy} style={{ padding: "10px 18px", borderRadius: 8 }}>
          Ask
        </button>
      </div>
    </div>
  );
}
