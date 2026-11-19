import { afterEach, expect, it, vi } from "vitest";
import { call, RpcError } from "./rpc";

// Restore fetch after every test so a stub cannot affect the next scenario.
afterEach(() => vi.unstubAllGlobals());

it("sends JSON-RPC params and returns the correlated result", async () => {
  // Inspect the outgoing envelope and echo its generated ID to model a valid server reply.
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    expect(url).toBe("/api/rpc");
    const request = JSON.parse(init.body as string);
    expect(request).toMatchObject({ jsonrpc: "2.0", method: "greet", params: { name: "Ada" } });
    return Response.json({ jsonrpc: "2.0", id: request.id, result: "Hello, Ada!" });
  }));
  await expect(call("greet", { name: "Ada" })).resolves.toBe("Hello, Ada!");
});

it("surfaces server errors", async () => {
  // A successful HTTP response can still carry a JSON-RPC application error.
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init: RequestInit) => {
    const { id } = JSON.parse(init.body as string);
    return Response.json({ jsonrpc: "2.0", id, error: { code: -32602, message: "Invalid params" } });
  }));
  await expect(call("greet", { name: " " })).rejects.toBeInstanceOf(RpcError);
});

it("rejects mismatched responses", async () => {
  // A result for another request must be rejected, even if its payload otherwise looks valid.
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ jsonrpc: "2.0", id: "wrong", result: "hi" })));
  await expect(call("greet", {})).rejects.toThrow("Invalid JSON-RPC response");
});

it("surfaces HTTP failures", async () => {
  // Transport failures must report the HTTP status without trying to parse an empty JSON body.
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
  await expect(call("greet", {})).rejects.toThrow("HTTP 503");
});
