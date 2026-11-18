import { StrictMode, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import { call } from "./rpc";
import "./style.css";

function App() {
  const [name, setName] = useState("world");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult("");
    try {
      setResult(await call("greet", { name }));
    } catch (error) {
      setError(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return <main>
    <p className="eyebrow">GIT-CENTRIC</p>
    <h1>A starting point for your workspace.</h1>
    <p>Call the Python library from your browser.</p>
    <form onSubmit={submit}>
      <label htmlFor="name">Name</label>
      <input id="name" value={name} onChange={e => setName(e.target.value)} required />
      <button disabled={busy || !name.trim()}>{busy ? "Calling…" : "Greet"}</button>
    </form>
    <p role="status">{result}</p>
    {error && <p role="alert">{error}</p>}
  </main>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
