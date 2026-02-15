import { useEffect, useState } from "react";
import type { HealthPayload } from "../shared/types";

export default function App() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const run = async () => {
      const result = await window.vault.health();
      if (result.ok) {
        setHealth(result.data);
        return;
      }
      setError(result.error.message);
    };
    void run();
  }, []);

  return (
    <main className="app-shell">
      <section className="panel">
        <h1>Prompt Vault</h1>
        <p>macOS desktop skeleton is ready.</p>
        <p>{health ? `${health.status} / ${health.mode}` : "checking health..."}</p>
        {health ? <p>DB: {health.dbPath}</p> : null}
        {error ? <p style={{ color: "#b91c1c" }}>{error}</p> : null}
      </section>
    </main>
  );
}
