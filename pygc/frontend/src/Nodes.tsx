import { useMemo, useState } from "react";
import { call, type PreviewAction, type RegistryNode } from "./rpc";
import { useRegistry, type Save } from "./useRegistry";

import { PreviewStatus, usePermissions } from "./Permissions";

const readNodes = () => call("nodes.list", {});

function NodeRow({ node, tip, save, mayRemove }: { node: RegistryNode; tip: string; save: Save; mayRemove?: boolean }) {
  // Keep the operator's draft separate from the committed URL shown after reload.
  const [draft, setDraft] = useState<string | null>(null);
  return <article className="content">
    <h3>{node.name}</h3>
    <p className="prose">{node.url}</p>
    {draft === null ? <div className="controls">
      <button onClick={() => setDraft(node.url)}>Edit URL</button>
      <button disabled={mayRemove !== true} onClick={() => {
        if (window.confirm(`Remove node “${node.name}” at ${node.url}?`))
          void save(() => call("nodes.remove", { name: node.name, expectedTip: tip }));
      }}>Remove node</button>
      {mayRemove === false && <small>Repository policy prevents removing this node.</small>}
    </div> : <form onSubmit={event => {
      event.preventDefault();
      void save(() => call("nodes.change_url", { name: node.name, url: draft, expectedTip: tip }),
        () => setDraft(null));
    }}>
      <label>New Git URL<input required value={draft} onChange={e => setDraft(e.target.value)} /></label>
      <div className="controls">
        <button className="primary" disabled={draft === node.url}>Save URL</button>
        <button type="button" onClick={() => setDraft(null)}>Cancel</button>
      </div>
    </form>}
  </article>;
}

export function Nodes({ onName, onSaved }: { onName: (name: string) => void; onSaved: () => void }) {
  const { snapshot, setup, loading, saving, review, error, save, reload } =
    useRegistry(readNodes, onName, onSaved, {
      invalid_argument: "Enter a valid node name and Git endpoint.",
      not_found: "This node no longer exists. Reload the list.",
    });
  const actions = useMemo<PreviewAction[]>(() => (snapshot?.nodes ?? []).map(node =>
    ({ name: "nodes.remove", node_id: node.name, url: node.url })), [snapshot]);
  const preview = usePermissions(actions, snapshot?.metadata_tip ?? "");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");

  return <section aria-label="Participating nodes">
    <h2>Participating nodes</h2>
    <PreviewStatus preview={preview} />
    {error && <p role="alert">{error} <button disabled={loading || saving} onClick={reload}>Reload</button></p>}
    {loading && <p role="status">Loading nodes…</p>}
    <fieldset disabled={loading || saving || review}>
      {setup && <article className="content">
        <p>Initialize this repository to register participating nodes.</p>
        <button onClick={() => save(() => call("repo.initialize", {}))}>Initialize repository</button>
      </article>}
      {snapshot && <>
        <form onSubmit={event => {
          event.preventDefault();
          void save(() => call("nodes.add", { name, url, expectedTip: snapshot.metadata_tip }),
            () => { setName(""); setUrl(""); });
        }}>
          <label>Node name<input required value={name} onChange={e => setName(e.target.value)} /></label>
          <label>Git URL or path<input required value={url} onChange={e => setUrl(e.target.value)} /></label>
          <button className="primary">Add node</button>
        </form>
        {!snapshot.nodes.length && <p>No nodes registered.</p>}
        {snapshot.nodes.map((node, index) => <NodeRow key={node.name} node={node} tip={snapshot.metadata_tip} save={save} mayRemove={preview.decisions?.[index]} />)}
      </>}
    </fieldset>
  </section>;
}
