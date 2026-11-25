import { executeDemo } from "@/lib/demo-run";

export default function AuditPage() {
  const snap = executeDemo();
  return (
    <main>
      <h1>Audit</h1>
      <p className="muted">Predicate failures among dropped survivors (post-dedupe)</p>
      <ul>
        {Object.entries(snap.byPredicate)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => (
            <li key={k}>
              <strong>{k}</strong>: {v}
            </li>
          ))}
      </ul>
      {snap.intentLines.length > 0 && (
        <>
          <h2>Fixture intent notes</h2>
          <ul className="muted">
            {snap.intentLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
      <h2>Outcome</h2>
      <p>
        POSSIBLE {snap.possible.length} · noise_dropped {snap.noiseDropped} · dedupe{" "}
        {snap.dedupeDropped}
      </p>
    </main>
  );
}