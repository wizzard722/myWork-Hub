import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type AuditEntry } from "../api";
import { Icon } from "../components/Icon";

const ACTIONS: { value: string; label: string }[] = [
  { value: "", label: "Alle handelingen" },
  { value: "auth.", label: "Inloggen en sessies" },
  { value: "user.", label: "Gebruikers" },
  { value: "theme.", label: "Thema" },
  { value: "tenant.", label: "Organisatie" },
  { value: "assistant.", label: "Assistent" },
  { value: "admin.", label: "Geweigerde beheertoegang" },
  { value: "audit.", label: "Auditlog" },
];

const LABELS: Record<string, string> = {
  "auth.login": "Ingelogd",
  "auth.login_failed": "Inloggen mislukt",
  "auth.logout": "Uitgelogd",
  "auth.session_reuse_detected": "Gestolen sessie geblokkeerd",
  "tenant.created": "Organisatie aangemaakt",
  "tenant.updated": "Organisatie gewijzigd",
  "user.created": "Gebruiker toegevoegd",
  "user.updated": "Gebruiker gewijzigd",
  "user.role_changed": "Rol gewijzigd",
  "user.activated": "Gebruiker ingeschakeld",
  "user.deactivated": "Gebruiker uitgeschakeld",
  "user.password_reset": "Wachtwoord opnieuw ingesteld",
  "user.password_changed": "Eigen wachtwoord gewijzigd",
  "user.deleted": "Gebruiker verwijderd",
  "theme.updated": "Thema gewijzigd",
  "theme.reset": "Standaardthema hersteld",
  "audit.exported": "Auditlog geëxporteerd",
  "assistant.tool_call": "Assistent voerde actie uit",
  "assistant.tool_declined": "Actie van assistent geweigerd",
};

const OUTCOME: Record<AuditEntry["outcome"], string> = {
  success: "Gelukt",
  denied: "Geweigerd",
  failure: "Mislukt",
};

function describe(entry: AuditEntry): string {
  const details = entry.details ?? {};
  const parts: string[] = [];
  if (typeof details.email === "string") parts.push(details.email);
  if (typeof details.reason === "string") parts.push(details.reason);
  const changes = details.changes as Record<string, unknown> | undefined;
  if (changes) {
    for (const [field, value] of Object.entries(changes)) {
      parts.push(Array.isArray(value) ? `${field}: ${value[0]} → ${value[1]}` : `${field}: ${String(value)}`);
    }
  }
  if (typeof details.tool === "string") parts.push(`${details.app ?? ""} ${details.tool}`.trim());
  return parts.join(" · ");
}

function actor(entry: AuditEntry): string {
  if (entry.actor_type === "system") return `Systeem (${entry.actor_email ?? "onbekend"})`;
  const who = entry.actor_email ?? "onbekend";
  return entry.actor_type === "assistant" ? `${who} via assistent` : who;
}

export function AuditPage() {
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [filter, setFilter] = useState({ action: "", actor: "", outcome: "" });
  const [error, setError] = useState<string | null>(null);
  const [verify, setVerify] = useState<string | null>(null);

  const load = useCallback(
    async (beforeId?: number) => {
      try {
        const page = await api.audit({ ...filter, limit: 50, before_id: beforeId });
        setItems((current) => (beforeId ? [...current, ...page.items] : page.items));
        setNext(page.next_before_id);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Auditlog laden mislukt");
      }
    },
    [filter],
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function checkIntegrity() {
    const result = await api.verifyAudit();
    setVerify(
      result.valid
        ? `Integriteit in orde: ${result.checked} regels gecontroleerd, niets gewijzigd of verwijderd.`
        : `Let op: het auditlog is aangepast vanaf regel ${result.first_invalid_id}.`,
    );
  }

  async function exportCsv() {
    const blob = await api.exportAudit();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "auditlog.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  return (
    <section className="section">
      <div className="row space-between">
        <h1>Auditlog</h1>
        <div className="row">
          <button type="button" className="button" onClick={() => void checkIntegrity()}>
            <Icon name="shield" size={16} /> Integriteit controleren
          </button>
          <button type="button" className="button" onClick={() => void exportCsv()}>
            Exporteren (CSV)
          </button>
        </div>
      </div>
      <p className="muted">
        Elke handeling van beheerders, gebruikers en de assistent: wie, wat, wanneer en
        waarvandaan. Regels kunnen niet worden gewijzigd of verwijderd.
      </p>
      {verify && (
        <p className={`notice ${verify.startsWith("Let op") ? "danger" : "ok"}`} role="status">
          {verify}
        </p>
      )}
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
      <form className="row filters" onSubmit={submit}>
        <label className="field">
          <span>Handeling</span>
          <select value={filter.action} onChange={(e) => setFilter({ ...filter, action: e.target.value })}>
            {ACTIONS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Door (e-mail)</span>
          <input value={filter.actor} onChange={(e) => setFilter({ ...filter, actor: e.target.value })} />
        </label>
        <label className="field">
          <span>Uitkomst</span>
          <select value={filter.outcome} onChange={(e) => setFilter({ ...filter, outcome: e.target.value })}>
            <option value="">Alle</option>
            <option value="success">Gelukt</option>
            <option value="denied">Geweigerd</option>
            <option value="failure">Mislukt</option>
          </select>
        </label>
      </form>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Tijdstip</th>
              <th scope="col">Door</th>
              <th scope="col">Handeling</th>
              <th scope="col">Details</th>
              <th scope="col">Uitkomst</th>
              <th scope="col">IP-adres</th>
            </tr>
          </thead>
          <tbody>
            {items.map((entry) => (
              <tr key={entry.id} title={`Request-ID: ${entry.request_id ?? "-"}`}>
                <td>{new Date(entry.occurred_at).toLocaleString("nl-NL")}</td>
                <td>{actor(entry)}</td>
                <td>{LABELS[entry.action] ?? entry.action}</td>
                <td className="wrap">{describe(entry)}</td>
                <td>
                  <span className={`badge ${entry.outcome === "success" ? "ok" : "invalid"}`}>
                    {OUTCOME[entry.outcome]}
                  </span>
                </td>
                <td>{entry.ip ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {items.length === 0 && !error && <p className="muted">Geen regels gevonden.</p>}
      {next && (
        <div>
          <button type="button" className="button" onClick={() => void load(next)}>
            Meer laden
          </button>
        </div>
      )}
    </section>
  );
}
