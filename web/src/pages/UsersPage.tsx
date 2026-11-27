import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type Role, type Session, type User } from "../api";

const roleLabel: Record<Role, string> = {
  owner: "Eigenaar",
  admin: "Beheerder",
  member: "Gebruiker",
};

export function UsersPage({ session }: { session: Session }) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", display_name: "", password: "", role: "member" as Role });
  const [saving, setSaving] = useState(false);
  const isOwner = session.user.role === "owner";

  const load = useCallback(() => {
    api
      .users()
      .then(setUsers)
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Er ging iets mis");
    }
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    await run(async () => {
      await api.createUser(form);
      setForm({ email: "", display_name: "", password: "", role: "member" });
    });
    setSaving(false);
  }

  const roles: Role[] = isOwner ? ["member", "admin", "owner"] : ["member", "admin"];

  return (
    <section className="section">
      <h1>Gebruikers</h1>
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Naam</th>
              <th scope="col">E-mailadres</th>
              <th scope="col">Rol</th>
              <th scope="col">Status</th>
              <th scope="col">
                <span className="visually-hidden">Acties</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {users?.map((user) => {
              const self = user.id === session.user.id;
              const locked = self || (user.role === "owner" && !isOwner);
              return (
                <tr key={user.id}>
                  <td>{user.display_name}</td>
                  <td>{user.email}</td>
                  <td>
                    <select
                      aria-label={`Rol van ${user.display_name}`}
                      value={user.role}
                      disabled={locked}
                      onChange={(e) =>
                        void run(() => api.updateUser(user.id, { role: e.target.value as Role }))
                      }
                    >
                      {(locked ? [user.role] : roles).map((role) => (
                        <option key={role} value={role}>
                          {roleLabel[role]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>{user.is_active ? "Actief" : "Uitgeschakeld"}</td>
                  <td>
                    {!locked && (
                      <div className="actions">
                        <button
                          type="button"
                          className="button small"
                          onClick={() =>
                            void run(() => api.updateUser(user.id, { is_active: !user.is_active }))
                          }
                        >
                          {user.is_active ? "Uitschakelen" : "Inschakelen"}
                        </button>
                        <button
                          type="button"
                          className="button small danger"
                          onClick={() => {
                            if (window.confirm(`${user.display_name} verwijderen?`))
                              void run(() => api.deleteUser(user.id));
                          }}
                        >
                          Verwijderen
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <form className="card form-grid" onSubmit={add} aria-labelledby="add-user">
        <h2 id="add-user">Gebruiker toevoegen</h2>
        <label className="field">
          <span>Naam</span>
          <input
            required
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
        </label>
        <label className="field">
          <span>E-mailadres</span>
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Wachtwoord (minimaal 12 tekens)</span>
          <input
            type="password"
            autoComplete="new-password"
            minLength={12}
            required
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Rol</span>
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            {roles.map((role) => (
              <option key={role} value={role}>
                {roleLabel[role]}
              </option>
            ))}
          </select>
        </label>
        <div>
          <button className="button primary" type="submit" disabled={saving}>
            Toevoegen
          </button>
        </div>
      </form>
    </section>
  );
}
