import { useEffect, useState } from "react";
import { call, RpcError } from "./rpc";

export type Save = (operation: () => Promise<unknown>, clear?: () => void) => Promise<void>;

export function useRegistry<T>(read: () => Promise<T>, onName: (name: string) => void,
  onSaved: () => void, messagesForRegistry: Record<string, string>) {
  const [snapshot, setSnapshot] = useState<T | null>(null);
  const [setup, setSetup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [review, setReview] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  function reload() {
    setLoading(true);
    setVersion(n => n + 1);
  }
  useEffect(() => {
    let active = true;
    async function load() {
      const context = await call("repo.get", {});
      if (!active) return;
      onName(context.name);
      const registry = context.initialized ? await read() : null;
      if (!active) return;
      setSetup(!context.initialized);
      setSnapshot(registry);
      setReview(false);
      setError("");
    }
    load().catch(() => {
      if (active) {
        setReview(true);
        setError("Could not load repository records. Reload to try again.");
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [version, onName, read]);

  const save: Save = async (operation, clear) => {
    if (loading || saving || review) return;
    setSaving(true);
    setError("");
    try {
      await operation();
      onSaved();
      clear?.();
      reload();
    } catch (e) {
      const reason = e instanceof RpcError ? e.reason : undefined;
      const messages: Record<string, string> = {
        stale_snapshot: "Repository records changed. Reload and review your changes before saving.",
        already_initialized: "Another session initialized this repository. Reload to see its records.",
        id_conflict: "That name is already registered.",
        access_denied: "Repository policy denied this change.",
        ...messagesForRegistry,
      };
      setReview(!reason || reason === "stale_snapshot" || reason === "already_initialized");
      setError(reason ? messages[reason] || `Repository operation failed (${reason}).` :
        "Could not confirm the operation. Reload to check the repository before trying again.");
    } finally {
      setSaving(false);
    }
  };
  return {snapshot, setup, loading, saving, review, error, save, reload};
}
