/** Explicit browser-facing contract; add library methods here and in Python's registry. */
export interface RepositoryContext {
  name: string;
  bare: boolean;
  branch: string | null;
  head: string | null;
  initialized: boolean;
  metadata_tip: string | null;
}

function isContext(value: unknown): value is RepositoryContext {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.name === "string" &&
    typeof v.bare === "boolean" &&
    typeof v.initialized === "boolean" &&
    [v.branch, v.head, v.metadata_tip].every(
      (field) => field === null || typeof field === "string",
    )
  );
}

type Commit = { id: string; title: string; author: string; date: string };
export type Item = {
  id: string;
  title: string;
  closed: boolean;
  author: string;
  created_at: string;
  base?: string;
  compare?: string;
  draft?: boolean;
  merged?: boolean;
};
export type Source = {
  name: string;
  branches: string[];
  branch: string | null;
  detached: boolean;
  commit: Commit | null;
  entries: { name: string; kind: string }[];
  text: string | null;
  notice: string | null;
  commits: Commit[];
  more: boolean;
  body?: string;
  patch?: string;
  changes?: FileChange[];
  parents?: string[];
};
const record = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object";
const nullable = (v: unknown) => v === null || typeof v === "string";
const commit = (v: unknown) =>
  record(v) &&
  ["id", "title", "author", "date"].every((k) => typeof v[k] === "string");
const strings = (v: unknown) =>
  Array.isArray(v) && v.every((s) => typeof s === "string");
const changes = (v: unknown) =>
  Array.isArray(v) &&
  v.every(
    (f) =>
      record(f) &&
      typeof f.path === "string" &&
      typeof f.status === "string" &&
      nullable(f.old_path),
  );
function source(v: unknown) {
  return (
    record(v) &&
    typeof v.name === "string" &&
    Array.isArray(v.branches) &&
    v.branches.every((b) => typeof b === "string") &&
    nullable(v.branch) &&
    typeof v.detached === "boolean" &&
    (v.commit === null || commit(v.commit)) &&
    Array.isArray(v.entries) &&
    v.entries.every(
      (e) =>
        record(e) && typeof e.name === "string" && typeof e.kind === "string",
    ) &&
    nullable(v.text) &&
    nullable(v.notice) &&
    Array.isArray(v.commits) &&
    v.commits.every(commit) &&
    typeof v.more === "boolean"
  );
}
export type Tab = "issues" | "pulls";
export type Comment = {
  id: string;
  text: string;
  author?: string;
  created_at?: string;
  replies_to: string[];
};
type FileChange = { status: string; path: string; old_path: string | null };
export type Detail = {
  issue?: Item;
  pull_request?: Item;
  metadata_tip: string;
  comments: Comment[];
  base_tip?: string | null;
  compare_tip?: string | null;
  changed_files?: FileChange[] | null;
  merge_analysis_error?: string | null;
  merge_conflicts?: boolean | null;
  conflicting_files?: string[] | null;
};
type ListFilters = {
  state?: "open" | "closed" | "all";
  title?: string;
  author?: string;
};
type Guard = { id: string; expectedTip: string };
type Endpoint<K extends string, P, R> = Record<K, { params: P; result: R }>;
export type AccessUser = { name: string; public_key: string };
export type AccessRole = { name: string; metadata: string; users: string[] };
export type AccessSnapshot = { metadata_tip: string; users: AccessUser[]; roles: AccessRole[] };
type Conditional = { expectedTip: string };
const accessUser = (v: unknown) => record(v) && typeof v.name === "string" && typeof v.public_key === "string";
const accessRole = (v: unknown) => record(v) && typeof v.name === "string" && typeof v.metadata === "string" && strings(v.users);

export type RegistryNode = { name: string; url: string };
export type NodeSnapshot = { metadata_tip: string; nodes: RegistryNode[] };
const registryNode = (v: unknown) => record(v) && typeof v.name === "string" && typeof v.url === "string";
type Methods = Endpoint<"nodes.list", Record<string, never>, NodeSnapshot> &
  Endpoint<"nodes.add" | "nodes.change_url", Conditional & RegistryNode, RegistryNode> &
  Endpoint<"nodes.remove", Conditional & { name: string }, RegistryNode> &
  Endpoint<"access.get", Record<string, never>, AccessSnapshot> &
  Endpoint<"access.users.add", Conditional & { name: string; publicKey: string }, AccessUser> &
  Endpoint<"access.roles.create", Conditional & { name: string; metadata?: string }, AccessRole> &
  Endpoint<"access.roles.delete", Conditional & { name: string }, AccessRole> &
  Endpoint<"access.roles.assign" | "access.roles.unassign", Conditional & { user: string; role: string }, AccessRole> &
  Endpoint<`${Tab}.show`, { id: string }, Detail> &
  Endpoint<
    `${Tab}.create`,
    { title: string; description: string; base?: string; compare?: string },
    Item
  > &
  Endpoint<
    `${Tab}.update`,
    Guard & {
      title?: string;
      base?: string;
      compare?: string;
      state?: "close" | "reopen";
      readiness?: "draft" | "ready";
    },
    Item
  > &
  Endpoint<
    `${Tab}.comments.add`,
    Guard & { text: string; repliesTo: string[] },
    Comment
  > &
  Endpoint<
    `${Tab}.comments.update`,
    Guard & { text: string; comment: string },
    Comment
  > &
  Endpoint<`${Tab}.comments.delete`, Guard & { comment: string }, Comment> &
  Endpoint<"repo.initialize", Record<string, never>, string> &
  Endpoint<
    "pulls.patch",
    { id: string; baseTip: string; compareTip: string; path: string },
    string
  > & {
    "code.browse": {
      params: {
        branch: string | null;
        path: string;
        revision: string | null;
        history: boolean;
        offset: number;
        detail?: boolean;
      };
      result: Source;
    };
    "issues.list": { params: ListFilters; result: Item[] };
    "pulls.list": { params: ListFilters; result: Item[] };
    "repo.get": { params: Record<string, never>; result: RepositoryContext };
    greet: { params: { name?: string }; result: string };
  };

export class RpcError extends Error {
  constructor(
    public readonly code: number,
    message: string,
    public readonly reason?: string,
  ) {
    super(message);
    this.name = "RpcError";
  }
}

export async function call<K extends keyof Methods>(
  method: K,
  params: Methods[K]["params"],
): Promise<Methods[K]["result"]> {
  const id = crypto.randomUUID();
  const response = await fetch("/api/rpc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", method, params, id }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data: unknown = await response.json();
  if (
    typeof data !== "object" ||
    data === null ||
    !("jsonrpc" in data) ||
    data.jsonrpc !== "2.0" ||
    !("id" in data) ||
    data.id !== id ||
    "result" in data === "error" in data
  )
    throw new Error("Invalid JSON-RPC response");
  if ("error" in data) {
    const error = data.error;
    if (
      typeof error !== "object" ||
      error === null ||
      !("code" in error) ||
      typeof error.code !== "number" ||
      !("message" in error) ||
      typeof error.message !== "string"
    ) {
      throw new Error("Invalid JSON-RPC error");
    }
    const detail = "data" in error ? error.data : undefined;
    const reason =
      detail &&
      typeof detail === "object" &&
      "reason" in detail &&
      typeof detail.reason === "string"
        ? detail.reason
        : undefined;
    throw new RpcError(error.code, error.message, reason);
  }
  // Validate the response against the requested method before returning it.
  const v = "result" in data ? data.result : undefined;
  const pulls = method.startsWith("pulls.");
  const item = (i: unknown) =>
    record(i) &&
    ["id", "title", "created_at", "author"].every(
      (k) => typeof i[k] === "string",
    ) &&
    typeof i.closed === "boolean" &&
    (!pulls ||
      (typeof i.base === "string" &&
        typeof i.compare === "string" &&
        typeof i.draft === "boolean" &&
        typeof i.merged === "boolean"));
  const comment = (c: unknown) =>
    record(c) &&
    typeof c.id === "string" &&
    typeof c.text === "string" &&
    strings(c.replies_to);
  function validResult() {
    if (method === "nodes.list")
      return record(v) && typeof v.metadata_tip === "string" && /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(v.metadata_tip)
        && Array.isArray(v.nodes) && v.nodes.every(registryNode);
    if (method.startsWith("nodes.")) return registryNode(v);
    if (method === "access.get")
      return record(v) && typeof v.metadata_tip === "string" && /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(v.metadata_tip)
        && Array.isArray(v.users) && v.users.every(accessUser)
        && Array.isArray(v.roles) && v.roles.every(accessRole);
    if (method === "access.users.add") return accessUser(v);
    if (method.startsWith("access.roles.")) return accessRole(v);
    if (method === "repo.get") return isContext(v);
    if (method === "code.browse")
      return (
        source(v) &&
        (!("detail" in params && params.detail) ||
          (record(v) &&
            (v.commit === null ||
              (typeof v.body === "string" &&
                typeof v.patch === "string" &&
                strings(v.parents) &&
                changes(v.changes)))))
      );
    if (["repo.initialize", "greet", "pulls.patch"].includes(method))
      return typeof v === "string";
    if (method.endsWith(".list")) return Array.isArray(v) && v.every(item);
    if (method.includes(".comments.")) return comment(v);
    if (method.endsWith(".show")) {
      if (
        !record(v) ||
        typeof v.metadata_tip !== "string" ||
        !Array.isArray(v.comments) ||
        !v.comments.every(
          (c) =>
            comment(c) &&
            record(c) &&
            typeof c.author === "string" &&
            typeof c.created_at === "string",
        )
      )
        return false;
      if (!pulls) return item(v.issue);
      return (
        item(v.pull_request) &&
        nullable(v.base_tip) &&
        nullable(v.compare_tip) &&
        nullable(v.merge_base) &&
        nullable(v.merge_analysis_error) &&
        (v.merge_conflicts === null ||
          typeof v.merge_conflicts === "boolean") &&
        (v.conflicting_files === null || strings(v.conflicting_files)) &&
        (v.changed_files === null || changes(v.changed_files))
      );
    }
    return item(v);
  }
  if (!validResult() || !("result" in data))
    throw new Error("Invalid JSON-RPC result");
  return data.result as Methods[K]["result"];
}
