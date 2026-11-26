import { useState } from "react";
import { noActions, PreviewStatus, usePermissions } from "./Permissions";
import { call, type PreviewAction, type Rule } from "./rpc";
import { useRegistry } from "./useRegistry";

const readRules = () => call("access.rules.list", {});
const permission: readonly PreviewAction[] = [{name: "access.rules.change_scripts"}];
const template = "def eval(action, user, roles):\n    return None\n";

export function Rules({onName, onSaved}: {
  onName: (name: string) => void; onSaved: () => void;
}) {
  const registry = useRegistry(readRules, onName, onSaved, {
    invalid_argument: "Use a rule-*.py filename and valid Python defining eval(action, user, roles).",
    not_found: "This rule no longer exists.",
  });
  const {snapshot, saving, loading, review, save} = registry;
  const preview = usePermissions(snapshot ? permission : noActions, snapshot?.metadata_tip ?? "");
  const allowed = preview.decisions?.[0] === true;
  const [original, setOriginal] = useState<Rule | null>(null);
  const [name, setName] = useState("");
  const [source, setSource] = useState(template);
  function select(rule: Rule | null) {
    setOriginal(rule);
    setName(rule?.name ?? "");
    setSource(rule?.source ?? template);
  }
  const current = snapshot?.rules.find(rule => rule.name === name);
  return <>
    {registry.error && <p role="alert">{registry.error} <button disabled={loading || saving} onClick={registry.reload}>Reload</button></p>}
    {loading && <p role="status">Loading rule scripts…</p>}
    {registry.setup && <button disabled={saving || loading} onClick={() => save(() => call("repo.initialize", {}))}>Initialize repository</button>}
    {snapshot && <>
      <PreviewStatus preview={preview} />
      {preview.decisions?.[0] === false && <p>Repository policy prevents changes to rule scripts.</p>}
      <fieldset disabled={saving || loading || review}>
        <label>Rule script
          <select value={original?.name ?? ""} onChange={e => select(snapshot.rules.find(rule => rule.name === e.target.value) ?? null)}>
            <option value="">New rule</option>
            {snapshot.rules.map(rule => <option key={rule.name}>{rule.name}</option>)}
          </select>
        </label>
        <form onSubmit={event => {
          event.preventDefault();
          if (allowed) void save(() => call("access.rules.change", {operation: original ? "edit" : "create",
            name, source, expectedTip: snapshot.metadata_tip}), () => select({name, source}));
        }}>
          <label>File name<input required readOnly={!!original || !allowed} value={name}
            placeholder="rule-example.py" onChange={e => setName(e.target.value)} /></label>
          <label>Python source<textarea className="rule-source" required rows={16} spellCheck={false} readOnly={!allowed}
            value={source} onChange={e => setSource(e.target.value)} /></label>
          {original && original.source !== current?.source && <details open>
            <summary>Current committed version</summary><pre>{current?.source ?? "This rule was deleted."}</pre>
          </details>}
          <div className="controls">
            <button className="primary" disabled={!allowed || (original ? !current || current.source === source : !name)}>
              {original ? "Save changes" : "Create rule"}
            </button>
            {original && <button type="button" disabled={!allowed || !current} onClick={() => {
              if (window.confirm(`Delete ${name}?`)) void save(() => call("access.rules.change",
                {operation: "delete", name, expectedTip: snapshot.metadata_tip}), () => select(null));
            }}>Delete rule</button>}
          </div>
        </form>
      </fieldset>
    </>}
  </>;
}
