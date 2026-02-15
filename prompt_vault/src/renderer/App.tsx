import { useEffect, useState } from "react";
import type { HealthPayload } from "../shared/types";

export default function App() {
  const [health, setHealth] = useState<HealthPayload | null>(null);

  useEffect(() => {
    const run = async () => {
      const result = await window.vault.health();
      setHealth(result);
    };
    void run();
  }, []);

  return (
    <main className="app-shell">
      <section className="panel">
        <h1>Prompt Vault</h1>
        <p>macOS only desktop skeleton is ready.</p>
        <p>{health ? `${health.status} / ${health.mode}` : "checking health..."}</p>
      </section>
    </main>
  );
}
