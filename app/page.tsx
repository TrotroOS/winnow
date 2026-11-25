import { Badge } from "@/components/Badge";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { StatGrid } from "@/components/StatGrid";
import { executeDemo } from "@/lib/demo-run";

export default function HomePage() {
  const snap = executeDemo();
  return (
    <main>
      <PageHeader
        title="Pipeline snapshot"
        description="Fixture-backed run through filter, dedupe, and staged outreach."
        meta={<Badge variant="accent">{snap.templateName}</Badge>}
      />
      <StatGrid
        items={[
          { label: "POSSIBLE", value: snap.possible.length, accent: true },
          { label: "Noise dropped", value: snap.noiseDropped },
          { label: "Dedupe dropped", value: snap.dedupeDropped },
          {
            label: "Outreach staged",
            value: snap.outreach.skipped,
            hint: "manual approve",
          },
        ]}
      />
      <Panel title="Situation">
        <dl className="kv-list">
          <div>
            <dt>Segment</dt>
            <dd>{snap.situation.segment}</dd>
          </div>
          <div>
            <dt>Product</dt>
            <dd>{snap.situation.product}</dd>
          </div>
          <div>
            <dt>Goal</dt>
            <dd>{snap.situation.goal}</dd>
          </div>
          <div>
            <dt>Criteria</dt>
            <dd>{snap.criteriaNames.join(", ")}</dd>
          </div>
          <div>
            <dt>Filter now</dt>
            <dd className="mono muted">{snap.filterNow}</dd>
          </div>
        </dl>
      </Panel>
      <Panel title="Message preview (first POSSIBLE)" flush>
        <pre className="pre-panel">{snap.preview || "(none)"}</pre>
      </Panel>
    </main>
  );
}