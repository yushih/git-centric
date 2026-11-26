import { useEffect, useState, type FormEvent } from "react";
import { call, RpcError, type AccessRole, type AccessSnapshot } from "./rpc";

type Save = (operation: () => Promise<unknown>, clear?: () => void) => Promise<void>;

function RoleRow({role, snapshot, save}: {role: AccessRole; snapshot: AccessSnapshot; save: Save}) {
  const [target, select] = useState("");
  const all = target === "*";
  const registered = snapshot.users.some(u => u.name === target);
  const assigned = role.users.includes(target);
  const params = {user: target, role: role.name, expectedTip: snapshot.metadata_tip};
  return <article className="content">
    <h3>{role.name}</h3>
    {role.metadata && <p className="prose">{role.metadata}</p>}
    <p>Members · {role.users.join(", ") || "None"}</p>
    <div className="controls">
      <label>User
        <select value={registered || all ? target : ""} onChange={e => select(e.target.value)}>
          <option value="">Choose a user</option>
          <option value="*">All users</option>
          {snapshot.users.map(u => <option key={u.name}>{u.name}</option>)}
        </select>
      </label>
      <button disabled={all ? role.users.length === snapshot.users.length : !registered || assigned}
        onClick={() => save(() => call("access.roles.assign", params))}>
        {all ? `Assign to ${snapshot.users.length - role.users.length} users` : "Assign"}
      </button>
      <button disabled={all ? !role.users.length : !registered || !assigned}
        onClick={() => save(() => call("access.roles.unassign", params))}>
        {all ? `Remove from ${role.users.length} users` : "Unassign"}
      </button>
    </div>
    {role.users.length ? <small>Remove all members to delete this role.</small> :
      <button onClick={() => {
        if (window.confirm(`Delete the role “${role.name}”?`))
          void save(() => call("access.roles.delete", {name: role.name, expectedTip: snapshot.metadata_tip}));
      }}>Delete role</button>}
  </article>;
}

export function Access({usersView, onName, onSaved}: {
  usersView: boolean; onName: (name: string) => void; onSaved: () => void;
}) {
  const [snapshot, setSnapshot] = useState<AccessSnapshot | null>(null);
  const [setup, setSetup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [review, setReview] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [roleName, setRoleName] = useState("");
  const [metadata, setMetadata] = useState("");
  const [userName, setUserName] = useState("");
  const [key, setKey] = useState("");
  function reload() {
    setLoading(true);
    setVersion(n => n + 1);
  }
  useEffect(() => {
    let active = true;
    async function load() {
      const context = await call("repo.get", {});
      if (!active) return;
      onName(context.name);
      const registry = context.initialized ? await call("access.get", {}) : null;
      if (!active) return;
      setSetup(!context.initialized);
      setSnapshot(registry);
      setReview(false);
      setError("");
    }
    load().catch(() => {
      if (active) {
        setReview(true);
        setError("Could not load access records. Reload to try again.");
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [version, onName]);

  const save: Save = async (operation, clear) => {
    if (loading || saving || review) return;
    setSaving(true);
    setError("");
    try {
      await operation();
      onSaved();
      clear?.();
      reload();
    } catch (e) {
      const reason = e instanceof RpcError ? e.reason : undefined;
      const messages: Record<string, string> = {
        stale_snapshot: "Repository records changed. Reload and review your changes before saving.",
        already_initialized: "Another session initialized this repository. Reload to see its records.",
        id_conflict: "That name is already registered.",
        invalid_argument: "Check the name, public key, or role membership and try again.",
        not_found: "The selected user or role could not be found.",
      };
      setReview(!reason || reason === "stale_snapshot" || reason === "already_initialized");
      setError(reason ? messages[reason] || `Access operation failed (${reason}).` :
        "Could not confirm the operation. Reload to check the repository before trying again.");
    } finally {
      setSaving(false);
    }
  };
  function create(event: FormEvent) {
    event.preventDefault();
    if (!snapshot) return;
    const expectedTip = snapshot.metadata_tip;
    if (usersView) {
      void save(() => call("access.users.add", {name: userName, publicKey: key, expectedTip}),
        () => { setUserName(""); setKey(""); });
    } else {
      void save(() => call("access.roles.create", {name: roleName, metadata, expectedTip}),
        () => { setRoleName(""); setMetadata(""); });
    }
  }
  return <section aria-label="Repository access">
    <h2>Access</h2>
    <nav className="pr-tabs" aria-label="Access views">
      <a href="#access" aria-current={!usersView ? "page" : undefined}>Roles</a>
      <a href="#access?view=users" aria-current={usersView ? "page" : undefined}>Users</a>
    </nav>
    {error && <p role="alert">{error} <button disabled={loading || saving} onClick={reload}>Reload</button></p>}
    {loading && <p role="status">Loading access records…</p>}
    <fieldset disabled={saving || loading || review}>
      {setup && <article className="content">
        <p>Initialize this repository to create the default roles and register the Git author as owner using a local Ed25519 key.</p>
        <button onClick={() => save(() => call("repo.initialize", {}))}>Initialize repository</button>
      </article>}
      {snapshot && <>
        <form onSubmit={create}>
          <h3>{usersView ? "Register user" : "Create role"}</h3>
          {usersView ? <>
            <label>User name<input required value={userName} onChange={e => setUserName(e.target.value)} /></label>
            <label>OpenSSH Ed25519 public key<textarea required value={key} onChange={e => setKey(e.target.value)} /></label>
          </> : <>
            <label>Role name<input required value={roleName} onChange={e => setRoleName(e.target.value)} /></label>
            <label>Metadata (optional)<textarea value={metadata} onChange={e => setMetadata(e.target.value)} /></label>
          </>}
          <button className="primary">{usersView ? "Register user" : "Create role"}</button>
        </form>
        {usersView ? <>
          {!snapshot.users.length && <p>No registered users.</p>}
          {snapshot.users.map(user => <article className="content" key={user.name}>
            <h3>{user.name}</h3>
            <p>Roles · {snapshot.roles.filter(r => r.users.includes(user.name)).map(r => r.name).join(", ") || "None"}</p>
            <details><summary>Public key</summary><p className="prose">{user.public_key}</p></details>
          </article>)}
        </> : <>
          {!snapshot.roles.length && <p>No roles.</p>}
          {snapshot.roles.map(role => <RoleRow key={role.name} role={role} snapshot={snapshot} save={save} />)}
        </>}
      </>}
    </fieldset>
  </section>;
}
