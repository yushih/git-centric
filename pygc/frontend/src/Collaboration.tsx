import { useEffect, useState, type FormEvent } from "react";
import { call, RpcError, type Detail, type Item, type Tab } from "./rpc";

function message(e: unknown) {
  if (e instanceof RpcError && e.reason === "stale_snapshot")
    return "This view has changed. Reload the conversation and review your draft.";
  return e instanceof RpcError && e.reason
    ? e.reason.replaceAll("_", " ")
    : e instanceof Error
    ? e.message
    : "Request failed";
}
function status(i: Item) {
  return [
    i.closed ? "Closed" : "Open",
    i.draft && "Draft",
    i.merged && "Merged",
  ]
    .filter(Boolean)
    .join(" · ");
}
function fields(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return Object.fromEntries(new FormData(event.currentTarget)) as Record<
    string,
    string
  >;
}
const sourceParams = {
  branch: null,
  path: "",
  revision: null,
  history: false,
  offset: 0,
};

export function Collaboration({
  tab,
  query,
  onName,
}: {
  tab: Tab;
  query: string;
  onName: (v: string) => void;
}) {
  const q = new URLSearchParams(query);
  const id = q.get("id"),
    creating = q.has("new"),
    pulls = tab === "pulls";
  const noun = pulls ? "pull request" : "issue",
    pageTitle = pulls ? "Pull requests" : "Issues";
  const [initialized, setup] = useState(false),
    [branches, setBranches] = useState<string[]>([]);
  const [items, setItems] = useState<Item[]>([]),
    [detail, setDetail] = useState<Detail | null>(null);
  const [busy, loading] = useState(true),
    [saving, setSaving] = useState(false);
  const [error, setError] = useState(""),
    [version, reload] = useState(0);
  const [editor, edit] = useState(""),
    [draft, write] = useState("");
  const [patch, setPatch] = useState("");
  const pinnedBase = q.get("baseTip"),
    pinnedCompare = q.get("compareTip");
  const files = q.get("view") === "files",
    path = q.get("file");
  const requestedState = q.get("state");
  const state =
    requestedState === "all" || (!pulls && requestedState === "closed")
      ? requestedState
      : "open";
  const author = q.get("author") || "",
    title = q.get("title") || "";
  function link(changes: Record<string, string | null>) {
    const next = new URLSearchParams(query);
    Object.entries(changes).forEach(([k, v]) =>
      v === null ? next.delete(k) : next.set(k, v),
    );
    return "#" + tab + (next.size ? "?" + next : "");
  }
  useEffect(() => {
    let active = true;
    loading(true);
    setError("");
    async function load() {
      const ctx = await call("repo.get", {});
      if (!active) return;
      onName(ctx.name);
      setup(ctx.initialized);
      if (!ctx.initialized) return;
      if (pulls && (creating || id)) {
        const source = await call("code.browse", sourceParams);
        if (active) setBranches(source.branches);
      }
      if (id) {
        const d = await call(`${tab}.show`, { id });
        if (active) setDetail(d);
        if (files && path && d.base_tip && d.compare_tip) {
          const value = await call("pulls.patch", {
            id,
            path,
            baseTip: pinnedBase || d.base_tip,
            compareTip: pinnedCompare || d.compare_tip,
          });
          if (active) setPatch(value);
        }
      } else if (!creating) {
        const rows = await call(`${tab}.list`, { state, title, author });
        if (active) setItems(rows);
      }
    }
    load()
      .catch((e) => {
        if (active) setError(message(e));
      })
      .finally(() => {
        if (active) loading(false);
      });
    return () => {
      active = false;
    };
  }, [
    tab,
    id,
    creating,
    pulls,
    version,
    files,
    path,
    pinnedBase,
    pinnedCompare,
    state,
    title,
    author,
    onName,
  ]);
  async function save(action: () => Promise<unknown>) {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await action();
      edit("");
      write("");
      reload((v) => v + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setSaving(false);
    }
  }
  function start(key: string, text = "") {
    edit(key);
    write(text);
  }
  const record = detail?.issue ?? detail?.pull_request;
  const guard = { id: id ?? "", expectedTip: detail?.metadata_tip ?? "" };
  const selects = (base?: string, compare?: string) => (
    <div className="controls">
      {(["base", "compare"] as const).map((k, i) => (
        <label key={k}>
          {i ? "Compare branch" : "Base branch"}
          <select
            name={k}
            required
            defaultValue={(i ? compare : base) ?? branches[i]}
          >
            {Array.from(
              new Set([
                ...(i && compare ? [compare] : !i && base ? [base] : []),
                ...branches,
              ]),
            ).map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
  function composer(
    key: string,
    action: () => Promise<unknown>,
    label: string,
  ) {
    return (
      editor === key && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save(action);
          }}
        >
          <label>
            {label}
            <textarea
              autoFocus
              aria-label={label}
              value={draft}
              onChange={(e) => write(e.target.value)}
            />
          </label>
          <div className="controls">
            <button className="primary">Save</button>
            <button type="button" onClick={() => edit("")}>
              Cancel
            </button>
          </div>
        </form>
      )
    );
  }
  function thread(parent: string | null): React.ReactNode {
    return detail?.comments
      .filter((c) => (c.replies_to[0] ?? null) === parent)
      .map((c) => (
        <section
          className="comment"
          id={"comment-" + c.id}
          key={c.id}
          tabIndex={-1}
        >
          <strong>{c.id === "main" ? "Description" : "Comment"}</strong>{" "}
          <small>{c.id !== "main" && c.id}</small>
          {c.replies_to.slice(1).map((t) => (
            <button
              key={t}
              onClick={() => document.getElementById("comment-" + t)?.focus()}
            >
              Also replies to {t}
            </button>
          ))}
          <p className="prose">
            {c.text || (c.id === "main" ? "No description." : "Empty comment.")}
          </p>
          <div className="controls">
            <button onClick={() => start("reply-" + c.id)}>Reply</button>
            <button onClick={() => start("edit-" + c.id, c.text)}>Edit</button>
            {c.id !== "main" && (
              <button
                onClick={() => {
                  if (confirm("Delete this comment?"))
                    void save(() =>
                      call(`${tab}.comments.delete`, {
                        ...guard,
                        comment: c.id,
                      }),
                    );
                }}
              >
                Delete
              </button>
            )}
          </div>
          {composer(
            "edit-" + c.id,
            () =>
              call(`${tab}.comments.update`, {
                ...guard,
                text: draft,
                comment: c.id,
              }),
            "Edit text",
          )}
          {composer(
            "reply-" + c.id,
            () =>
              call(`${tab}.comments.add`, {
                ...guard,
                text: draft,
                repliesTo: [c.id],
              }),
            "Reply",
          )}
          {thread(c.id)}
        </section>
      ));
  }
  return (
    <>
      <div className="heading">
        <h1>
          {id || creating ? (
            <a href={link({ id: null, new: null, view: null, file: null })}>
              {pageTitle}
            </a>
          ) : (
            pageTitle
          )}
        </h1>
        {initialized && !creating && !id && (
          <a className="primary" href={link({ new: "1" })}>
            New {noun}
          </a>
        )}
      </div>
      {error && (
        <p role="alert">
          {error}{" "}
          <button
            onClick={() =>
              path
                ? (location.hash = link({
                    file: null,
                    baseTip: null,
                    compareTip: null,
                  }))
                : reload((v) => v + 1)
            }
          >
            Reload
          </button>
        </p>
      )}
      {busy && <p role="status">Loading…</p>}
      {(!busy || version > 0) && (
        <fieldset disabled={saving || busy}>
          {!initialized ? (
            !error && (
              <article>
                <h2>Set up collaboration</h2>
                <p>
                  Initialize this repository to track issues and pull requests.
                </p>
                <button onClick={() => save(() => call("repo.initialize", {}))}>
                  Initialize repository
                </button>
              </article>
            )
          ) : creating ? (
            <article>
              <h2>New {noun}</h2>
              <form
                onSubmit={(e) => {
                  const f = fields(e);
                  void save(async () => {
                    const item = await call(`${tab}.create`, {
                      title: f.title,
                      description: f.description,
                      ...(pulls ? { base: f.base, compare: f.compare } : {}),
                    });
                    location.hash = link({ new: null, id: item.id });
                  });
                }}
              >
                {pulls && selects()}
                <label>
                  Title
                  <input required name="title" />
                </label>
                <label>
                  Description
                  <textarea name="description" />
                </label>
                {pulls && branches.length < 2 && (
                  <p>Create two source branches to open a pull request.</p>
                )}
                <button
                  disabled={pulls && branches.length < 2}
                  className="primary"
                >
                  Create {noun}
                </button>
              </form>
            </article>
          ) : id && detail && record ? (
            <article>
              <h2>{record.title}</h2>
              <div className="content">
                <small>
                  {record.id} · {status(record)} · {record.author} ·{" "}
                  {record.created_at}
                </small>
                {pulls && (
                  <p>
                    {record.compare} → {record.base}
                  </p>
                )}
                {pulls && (
                  <nav className="controls">
                    <a href={link({ view: null, file: null })}>Conversation</a>
                    <a href={link({ view: "files", file: null })}>
                      Files changed
                    </a>
                  </nav>
                )}
                {files && pulls ? (
                  <>
                    <h3>Files changed</h3>
                    {detail.merge_analysis_error ? (
                      <p>
                        Comparison unavailable. {detail.merge_analysis_error}
                      </p>
                    ) : (
                      <>
                        <p>
                          {detail.merge_conflicts
                            ? "Conflicts in " +
                              detail.conflicting_files?.join(", ")
                            : "No merge conflicts"}
                        </p>
                        {detail.changed_files?.length === 0 && (
                          <p>No files changed.</p>
                        )}
                        {detail.changed_files?.map((f) => (
                          <div className="row" key={f.path}>
                            <a
                              href={link({
                                file: f.path,
                                baseTip: detail.base_tip ?? null,
                                compareTip: detail.compare_tip ?? null,
                              })}
                            >
                              {f.old_path && f.old_path + " → "}
                              {f.path}
                            </a>
                            <small>{f.status}</small>
                          </div>
                        ))}
                        {path && !error && (
                          <>
                            <h3>{path}</h3>
                            <pre>{patch || "No patch content."}</pre>
                          </>
                        )}
                      </>
                    )}
                  </>
                ) : (
                  <>
                    <div className="controls">
                      <button onClick={() => start("fields", record.title)}>
                        Edit {noun}
                      </button>
                      <button
                        onClick={() =>
                          save(() =>
                            call(`${tab}.update`, {
                              ...guard,
                              state: record.closed ? "reopen" : "close",
                            }),
                          )
                        }
                      >
                        {record.closed ? "Reopen" : "Close"} {noun}
                      </button>
                      {pulls && (
                        <button
                          onClick={() =>
                            save(() =>
                              call("pulls.update", {
                                ...guard,
                                readiness: record.draft ? "ready" : "draft",
                              }),
                            )
                          }
                        >
                          {record.draft ? "Mark ready" : "Convert to draft"}
                        </button>
                      )}
                    </div>
                    {editor === "fields" && (
                      <form
                        onSubmit={(e) => {
                          const f = fields(e);
                          void save(() =>
                            call(`${tab}.update`, {
                              ...guard,
                              title: draft,
                              ...(pulls
                                ? { base: f.base, compare: f.compare }
                                : {}),
                            }),
                          );
                        }}
                      >
                        <label>
                          Title
                          <input
                            required
                            value={draft}
                            onChange={(e) => write(e.target.value)}
                          />
                        </label>
                        {pulls && selects(record.base, record.compare)}
                        <button>Save changes</button>
                        <button type="button" onClick={() => edit("")}>
                          Cancel
                        </button>
                      </form>
                    )}
                    {thread(null)}
                    <button onClick={() => start("add")}>Add comment</button>
                    {composer(
                      "add",
                      () =>
                        call(`${tab}.comments.add`, {
                          ...guard,
                          text: draft,
                          repliesTo: [],
                        }),
                      "Comment",
                    )}
                  </>
                )}
              </div>
            </article>
          ) : (
            !id && (
              <>
                <form
                  className="filters"
                  onSubmit={(e) => {
                    const f = fields(e);
                    location.hash = link(f);
                  }}
                >
                  <label>
                    Status
                    <select name="state" defaultValue={state}>
                      <option value="open">Open</option>
                      {!pulls && <option value="closed">Closed</option>}
                      <option value="all">All</option>
                    </select>
                  </label>
                  <label>
                    Title
                    <input name="title" defaultValue={title} />
                  </label>
                  <label>
                    Author
                    <input name="author" defaultValue={author} />
                  </label>
                  <button>Filter</button>
                </form>
                <article>
                  {items.length
                    ? items.map((i) => (
                        <div className="row" key={i.id}>
                          <a href={link({ id: i.id })}>{i.title}</a>
                          <small>
                            {status(i)} · {i.author}
                          </small>
                        </div>
                      ))
                    : !error && <p>No matching {pageTitle.toLowerCase()}.</p>}
                </article>
              </>
            )
          )}
        </fieldset>
      )}
    </>
  );
}
