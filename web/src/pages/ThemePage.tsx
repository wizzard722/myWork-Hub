import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type Theme } from "../api";
import { useTheme, useThemeReload } from "../theme/ThemeProvider";

const COLOR_FIELDS = [
  { key: "primary", label: "Hoofdkleur" },
  { key: "primary_contrast", label: "Tekst op hoofdkleur" },
  { key: "background", label: "Achtergrond" },
  { key: "surface", label: "Vlakken" },
  { key: "text", label: "Tekst" },
] as const;

export function ThemePage() {
  const current = useTheme();
  const reload = useThemeReload();
  const [draft, setDraft] = useState<Theme>(current);
  const [message, setMessage] = useState<{ kind: "ok" | "danger"; text: string } | null>(null);

  useEffect(() => setDraft(current), [current]);

  const light = draft.light ?? {};
  const setColor = (key: string, value: string) =>
    setDraft({ ...draft, light: { ...light, [key]: value } });

  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await api.saveTheme({ ...draft, logo_url: draft.logo_url || null });
      setMessage({ kind: "ok", text: "Thema opgeslagen" });
      reload();
    } catch (e) {
      setMessage({ kind: "danger", text: e instanceof ApiError ? e.message : "Opslaan mislukt" });
    }
  }

  async function reset() {
    await api.resetTheme();
    setMessage({ kind: "ok", text: "Standaardthema hersteld" });
    reload();
  }

  return (
    <section className="section">
      <h1>Thema</h1>
      <p className="muted">
        Het thema geldt voor de hele hub van jullie organisatie, ook voor alle apps.
      </p>
      {message && (
        <p className={`notice ${message.kind}`} role="status">
          {message.text}
        </p>
      )}
      <form className="card form-grid" onSubmit={save}>
        <label className="field">
          <span>Naam van de hub</span>
          <input
            required
            maxLength={80}
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Logo (https-adres, optioneel)</span>
          <input
            type="url"
            placeholder="https://…"
            value={draft.logo_url ?? ""}
            onChange={(e) => setDraft({ ...draft, logo_url: e.target.value })}
          />
        </label>
        {COLOR_FIELDS.map((field) => (
          <label className="field color" key={field.key}>
            <span>{field.label}</span>
            <input
              type="color"
              value={light[field.key] ?? "#000000"}
              onChange={(e) => setColor(field.key, e.target.value)}
            />
          </label>
        ))}
        <div className="row">
          <button className="button primary" type="submit">
            Opslaan
          </button>
          <button className="button" type="button" onClick={() => void reset()}>
            Standaardthema
          </button>
        </div>
      </form>
    </section>
  );
}
