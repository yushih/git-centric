import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { FinalizationPanel, readFinalization, type FinalizationStatus } from "./Finalization";

afterEach(() => vi.unstubAllGlobals());

it("reads a noncached status without scheduling a round", async () => {
  const status = {state: "running", pending: true, tip: null, warnings: [], error: null};
  const fetch = vi.fn().mockResolvedValue(Response.json(status));
  vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal;
  expect(await readFinalization(signal)).toEqual(status);
  expect(fetch).toHaveBeenCalledWith("/api/finalization", {signal, cache: "no-store"});
  fetch.mockResolvedValue(Response.json({...status, state: "unknown"}));
  await expect(readFinalization(signal)).rejects.toThrow("Invalid finalization status");
});

it("renders queued work, round warnings and independent submission failures", () => {
  function panel(status: FinalizationStatus, triggerError = false) {
    return renderToStaticMarkup(<FinalizationPanel status={status} triggerError={triggerError}
      pollError={false} trigger={() => {}} />);
  }
  const running: FinalizationStatus = {state: "running", pending: true, tip: null, warnings: [], error: null};
  expect(panel(running)).toContain("Follow-up queued");
  const done = panel({...running, state: "not_finalized", pending: false, warnings: ["peer unreachable"]}, true);
  expect(done).toContain("No finality");
  expect(done).toContain("peer unreachable");
  expect(done).toContain("Action saved.");
});
