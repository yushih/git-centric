import { useEffect, useRef, useState } from "react";

const endpoint = "/api/finalization";
const labels = {
  idle: "No web round requested",
  running: "Running",
  finalized: "Finalized",
  not_finalized: "No finality",
  conflict: "Conflict majority",
  failed: "Failed",
};

export type FinalizationStatus = {
  state: keyof typeof labels;
  pending: boolean;
  tip: string | null;
  warnings: string[];
  error: string | null;
};

export async function readFinalization(signal: AbortSignal): Promise<FinalizationStatus> {
  const response = await fetch(endpoint, { signal, cache: "no-store" });
  if (!response.ok) throw Error("Could not read finalization status.");
  const data = await response.json();
  if (
    !data || !Object.hasOwn(labels, data.state) || typeof data.pending !== "boolean" ||
    !(data.tip === null || typeof data.tip === "string") ||
    !(data.error === null || typeof data.error === "string") ||
    !Array.isArray(data.warnings) || !data.warnings.every((w: unknown) => typeof w === "string")
  ) throw Error("Invalid finalization status.");
  return data;
}

export function useFinalization() {
  const [status, setStatus] = useState<FinalizationStatus | null>(null);
  const [pollError, setPollError] = useState(false);
  const [triggerError, setTriggerError] = useState(false);
  const lastRequest = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await readFinalization(AbortSignal.any([
          controller.signal, AbortSignal.timeout(5000),
        ]));
        if (!controller.signal.aborted) {
          setStatus(result);
          setPollError(false);
        }
      } catch {
        if (!controller.signal.aborted) setPollError(true);
      } finally {
        // Schedule from completion so slow connections never accumulate requests.
        if (!controller.signal.aborted) timer = setTimeout(poll, 1000);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);

  function trigger() {
    // A save is already committed. A scheduling failure belongs in the header,
    // and must never reject the save or interrupt its navigation/refresh.
    const sequence = ++lastRequest.current;
    void fetch(endpoint, { method: "POST", signal: AbortSignal.timeout(5000) })
      .then((response) => {
        if (sequence === lastRequest.current) setTriggerError(response.status !== 202);
      })
      .catch(() => {
        if (sequence === lastRequest.current) setTriggerError(true);
      });
  }
  return { status, pollError, triggerError, trigger };
}

export function FinalizationPanel({
  status, pollError, triggerError, trigger,
}: ReturnType<typeof useFinalization>) {
  return (
    <section className="finalization" aria-label="Finalization">
      <div role="status">
        <strong>Finalization</strong>{" · "}
        {pollError ? "Status unavailable" : status ? labels[status.state] : "Checking…"}
        {!pollError && status?.pending && " · Follow-up queued"}
        {!pollError && status?.tip && <code title={status.tip}> · {status.tip.slice(0, 8)}</code>}
      </div>
      {!pollError && status?.error && <small>{status.error.replaceAll("_", " ")}</small>}
      {!pollError && !!status?.warnings.length && (
        <details><summary>Round warnings ({status.warnings.length})</summary>
          <ul>{status.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
        </details>
      )}
      {triggerError && <div role="alert">
        Action saved. Could not confirm the finalization request.{" "}
        <button onClick={trigger}>Retry finalization</button>
      </div>}
    </section>
  );
}
