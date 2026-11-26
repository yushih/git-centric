import { useEffect, useState } from "react";
import { call, type PreviewAction } from "./rpc";

export const noActions: readonly PreviewAction[] = [];
export const createIssue: readonly PreviewAction[] = [{ name: "issues.create" }];
export const addIssueComment: readonly PreviewAction[] = [{ name: "issues.comments.add" }];
export const createRole: readonly PreviewAction[] = [{ name: "access.roles.create" }];

type Preview = {
  actions: readonly PreviewAction[];
  revision: string | number;
  attempt: number;
  decisions: boolean[] | null;
};

// Callers supply stable actions and the revision of the data used to build them.
// Ignore obsolete results during render as well as on completion: an effect's
// cleanup happens after the first render of a new route or snapshot.
export function usePermissions(actions: readonly PreviewAction[], revision: string | number) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Preview | null>(null);
  useEffect(() => {
    if (!actions.length) return;
    let active = true;
    function finish(decisions: boolean[] | null) {
      if (active) setResult({ actions, revision, attempt, decisions });
    }
    call("permissions.preview", { actions }).then(finish, () => finish(null));
    return () => { active = false; };
  }, [actions, revision, attempt]);
  const current = result?.actions === actions && result.revision === revision &&
    result.attempt === attempt ? result : null;
  return {
    decisions: current?.decisions,
    pending: actions.length > 0 && !current,
    failed: actions.length > 0 && current?.decisions === null,
    retry: () => setAttempt(n => n + 1),
  };
}

export function PreviewStatus({ preview }: { preview: ReturnType<typeof usePermissions> }) {
  if (preview.failed) return <p role="alert">Could not check permissions.{" "}
    <button type="button" onClick={preview.retry}>Retry permission check</button></p>;
  return preview.pending ? <p role="status">Checking permissions…</p> : null;
}
