import { Badge } from "@/components/Badge";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { StatGrid } from "@/components/StatGrid";
import { executeDemo } from "@/lib/demo-run";

export default function AuditPage() {
  const snap = executeDemo();
  const predicates = Object.entries(snap.byPredicate).sort(([a], [b]) => a.localeCompare(b));
  return (
    <main>
      <PageHeader
        title="Audit"
        description="Why survivors were dropped after dedupe — first failing predicate per candidate."
      />
      <Panel title="Predicate failures (dropped survivors)">
        {predicates.length === 0 ? (
          <p className="muted">No dropped survivors to audit.</p>
        ) : (
          <ul className="chip-list">
            {predicates.map(([k, v]) => (
              <li key={k}>
                <span className="chip">{k}</span>
                <span className="chip-count">×{v}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      {snap.intentLines.length > 0 && (
        <Panel title="Fixture intent notes">
          <ul className="note-list muted">
            {snap.intentLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Panel>
      )}
      <section>
        <h2 className="section-title">Outcome</h2>
        <StatGrid
          items={[
            { label: "POSSIBLE", value: snap.possible.length, accent: true },
            { label: "Noise dropped", value: snap.noiseDropped },
            { label: "Dedupe dropped", value: snap.dedupeDropped },
          ]}
        />
      </section>
      <div className="page-header__meta">
        <Badge variant="neutral">binary labels only</Badge>
      </div>
    </main>
  );
}