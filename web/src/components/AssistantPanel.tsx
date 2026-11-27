import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, assistant, type AssistantAction, type AssistantTurn } from "../api";
import { Icon } from "./Icon";

type Entry =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; actions: AssistantAction[] }
  | { kind: "error"; text: string };

const STATUS: Record<AssistantAction["status"], string> = {
  executed: "Uitgevoerd",
  failed: "Mislukt",
  declined: "Geweigerd",
  needs_confirmation: "Wacht op bevestiging",
  rejected: "Niet toegestaan",
};

function summary(input: Record<string, unknown>): string {
  return Object.entries(input)
    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(", ");
}

/** Assistent-paneel: een taalmodel dat apps bedient binnen de rechten van de gebruiker.
 *  Wijzigende acties worden pas uitgevoerd na bevestiging. */
export function AssistantPanel({ onClose }: { onClose: () => void }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [pending, setPending] = useState<AssistantAction[]>([]);
  const [conversation, setConversation] = useState<string | undefined>();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Accolades nodig: nieuwere browsers geven hier een Promise terug, die React anders
    // als opruimfunctie zou aanroepen.
    void end.current?.scrollIntoView?.({ block: "end" });
  }, [entries, pending, busy]);

  function apply(turn: AssistantTurn) {
    setConversation(turn.conversation_id);
    setPending(turn.pending);
    setEntries((e) => [...e, { kind: "assistant", text: turn.reply, actions: turn.actions }]);
  }

  async function run(action: () => Promise<AssistantTurn>) {
    setBusy(true);
    try {
      apply(await action());
    } catch (e) {
      setEntries((x) => [
        ...x,
        { kind: "error", text: e instanceof ApiError ? e.message : "De assistent is niet bereikbaar." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setEntries((e) => [...e, { kind: "user", text: message }]);
    setPending([]);
    await run(() => assistant.chat(message, conversation));
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  async function decide(approve: boolean) {
    if (!conversation) return;
    const decisions = Object.fromEntries(pending.map((p) => [p.id, approve]));
    setPending([]);
    await run(() => assistant.decide(conversation, decisions));
  }

  return (
    <aside className="assistant" aria-label="Assistent">
      <header className="assistant-head">
        <strong>
          <Icon name="sparkle" size={18} /> Assistent
        </strong>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Assistent sluiten">
          <Icon name="close" />
        </button>
      </header>
      <div className="assistant-log" aria-live="polite">
        {entries.length === 0 && (
          <p className="muted small">
            Vraag me iets te doen in je apps, bijvoorbeeld "Welke apps heb ik?" of "Begroet Sanne".
            Ik werk met jouw rechten en vraag eerst om bevestiging voordat ik iets wijzig.
          </p>
        )}
        {entries.map((entry, i) =>
          entry.kind === "user" ? (
            <p key={i} className="bubble user">
              {entry.text}
            </p>
          ) : entry.kind === "error" ? (
            <p key={i} className="notice danger" role="alert">
              {entry.text}
            </p>
          ) : (
            <div key={i} className="bubble bot">
              {entry.actions.length > 0 && (
                <ul className="action-list">
                  {entry.actions.map((a) => (
                    <li key={a.id} className={`action ${a.status}`}>
                      {a.app}: {a.tool} — {STATUS[a.status]}
                    </li>
                  ))}
                </ul>
              )}
              {entry.text && <p>{entry.text}</p>}
            </div>
          ),
        )}
        {pending.length > 0 && (
          <div className="confirm card" role="group" aria-label="Bevestiging nodig">
            <strong>Bevestiging nodig</strong>
            <ul>
              {pending.map((p) => (
                <li key={p.id}>
                  <span>{p.title}</span>
                  <span className="muted small">
                    {p.app} · {summary(p.input) || "geen invoer"}
                  </span>
                </li>
              ))}
            </ul>
            <div className="row">
              <button type="button" className="button primary" onClick={() => void decide(true)} disabled={busy}>
                Uitvoeren
              </button>
              <button type="button" className="button" onClick={() => void decide(false)} disabled={busy}>
                Weigeren
              </button>
            </div>
          </div>
        )}
        {busy && <p className="muted small">Bezig…</p>}
        <div ref={end} />
      </div>
      <form className="assistant-input" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="assistant-message">
          Bericht aan de assistent
        </label>
        <textarea
          id="assistant-message"
          rows={2}
          placeholder="Vraag de assistent…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
        />
        <button type="submit" className="icon-button send" aria-label="Versturen" disabled={busy || !text.trim()}>
          <Icon name="send" />
        </button>
      </form>
    </aside>
  );
}
