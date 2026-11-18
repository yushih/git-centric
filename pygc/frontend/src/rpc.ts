/** Explicit browser-facing contract; add library methods here and in Python's registry. */
interface Methods {
  greet: { params: { name?: string }; result: string };
}

export class RpcError extends Error {
  constructor(public readonly code: number, message: string) {
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
    throw new RpcError(error.code, error.message);
  }
  // All current methods return strings. Extend validation alongside Methods.
  if (!("result" in data) || typeof data.result !== "string") {
    throw new Error("Invalid JSON-RPC result");
  }
  return data.result;
}
