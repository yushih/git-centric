import { useMemo, useState, type FormEvent } from "react";
import { call, type AccessRole, type AccessSnapshot } from "./rpc";

import { useRegistry, type Save } from "./useRegistry";

import { createRole, noActions, PreviewStatus, usePermissions } from "./Permissions";

import { Rules } from "./Rules";

const readAccess = () => call("access.get", {});

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

function AccessRecords({usersView, onName, onSaved}: {
  usersView: boolean; onName: (name: string) => void; onSaved: () => void;
}) {
  const {snapshot, setup, loading, saving, review, error, save, reload} =
    useRegistry(readAccess, onName, onSaved, {
      invalid_argument: "Check the name, public key, or role membership and try again.",
      not_found: "The selected user or role could not be found.",
    });
  const actions = useMemo(() => snapshot && !usersView ? [...createRole] : noActions, [snapshot, usersView]);
  const preview = usePermissions(actions, snapshot?.metadata_tip ?? "");
  const restricted = !usersView && preview.decisions?.[0] !== true;
  const [roleName, setRoleName] = useState("");
  const [metadata, setMetadata] = useState("");
  const [userName, setUserName] = useState("");
  const [key, setKey] = useState("");
  function create(event: FormEvent) {
    event.preventDefault();
    if (!snapshot || restricted) return;
    const expectedTip = snapshot.metadata_tip;
    if (usersView) {
      void save(() => call("access.users.add", {name: userName, publicKey: key, expectedTip}),
        () => { setUserName(""); setKey(""); });
    } else {
      void save(() => call("access.roles.create", {name: roleName, metadata, expectedTip}),
        () => { setRoleName(""); setMetadata(""); });
    }
  }
  return <>
    <PreviewStatus preview={preview} />
    {preview.decisions?.[0] === false && <p>Repository policy prevents creating roles.</p>}
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
            <label>Role name<input disabled={restricted} required value={roleName} onChange={e => setRoleName(e.target.value)} /></label>
            <label>Metadata (optional)<textarea disabled={restricted} value={metadata} onChange={e => setMetadata(e.target.value)} /></label>
          </>}
          <button className="primary" disabled={restricted}>{usersView ? "Register user" : "Create role"}</button>
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
  </>;
}

export function Access({view, onName, onSaved}: {
  view: string | null; onName: (name: string) => void; onSaved: () => void;
}) {
  return <section aria-label="Repository access">
    <h2>Access</h2>
    <nav className="pr-tabs" aria-label="Access views">
      <a href="#access" aria-current={view !== "users" && view !== "rules" ? "page" : undefined}>Roles</a>
      <a href="#access?view=users" aria-current={view === "users" ? "page" : undefined}>Users</a>
      <a href="#access?view=rules" aria-current={view === "rules" ? "page" : undefined}>Rules</a>
    </nav>
    {view === "rules" ? <Rules onName={onName} onSaved={onSaved} /> :
      <AccessRecords usersView={view === "users"} onName={onName} onSaved={onSaved} />}
  </section>;
}
