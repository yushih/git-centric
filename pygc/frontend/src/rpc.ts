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
  return typeof v.name === "string" && typeof v.bare === "boolean" &&
    typeof v.initialized === "boolean" && [v.branch, v.head, v.metadata_tip].every(
      field => field === null || typeof field === "string"
    );
}

type Commit = { id:string; title:string; author:string; date:string };
export type Item = { id:string; title:string; closed:boolean };
export type Source = { name:string; branches:string[]; branch:string|null; detached:boolean;
  commit:Commit|null; entries:{name:string;kind:string}[]; text:string|null;
  notice:string|null; commits:Commit[]; more:boolean };
const record = (v:unknown): v is Record<string,unknown> => !!v && typeof v === "object";
const nullable = (v:unknown) => v === null || typeof v === "string";
const commit = (v:unknown) => record(v) && ["id","title","author","date"].every(k => typeof v[k] === "string");
function source(v:unknown) {
  return record(v) && typeof v.name === "string" && Array.isArray(v.branches) &&
    v.branches.every(b => typeof b === "string") && nullable(v.branch) && typeof v.detached === "boolean" &&
    (v.commit === null || commit(v.commit)) && Array.isArray(v.entries) &&
    v.entries.every(e => record(e) && typeof e.name === "string" && typeof e.kind === "string") &&
    nullable(v.text) && nullable(v.notice) && Array.isArray(v.commits) && v.commits.every(commit) &&
    typeof v.more === "boolean";
}
interface Methods {
  "code.browse": { params:{branch:string|null;path:string;revision:string|null;history:boolean;offset:number}; result:Source };
  "issues.list": {params:Record<string,never>;result:Item[]};
  "pulls.list": {params:Record<string,never>;result:Item[]};
  "repo.get": { params: Record<string, never>; result: RepositoryContext };
  greet: { params: { name?: string }; result: string };
}

export class RpcError extends Error {
  constructor(public readonly code: number, message: string, public readonly reason?: string) {
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
    typeof data !== "object" || data === null ||
    !("jsonrpc" in data) || data.jsonrpc !== "2.0" ||
    !("id" in data) || data.id !== id ||
    ("result" in data) === ("error" in data)
  ) throw new Error("Invalid JSON-RPC response");
  if ("error" in data) {
    const error = data.error;
    if (typeof error !== "object" || error === null ||
        !("code" in error) || typeof error.code !== "number" ||
        !("message" in error) || typeof error.message !== "string") {
      throw new Error("Invalid JSON-RPC error");
    }
    const detail = "data" in error ? error.data : undefined;
    const reason = detail && typeof detail === "object" && "reason" in detail &&
      typeof detail.reason === "string" ? detail.reason : undefined;
    throw new RpcError(error.code, error.message, reason);
  }
  // Validate the response against the requested method before returning it.
  if (!("result" in data) || (method === "repo.get" ? !isContext(data.result) :
      method === "code.browse" ? !source(data.result) :
      method === "greet" ? typeof data.result !== "string" :
      !Array.isArray(data.result) || !data.result.every(i => record(i) && typeof i.id === "string" &&
        typeof i.title === "string" && typeof i.closed === "boolean"))) {
    throw new Error("Invalid JSON-RPC result");
  }
  return data.result as Methods[K]["result"];
}
