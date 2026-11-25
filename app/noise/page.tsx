import { Banner } from "@/components/Banner";
import { Badge } from "@/components/Badge";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { readFileSync } from "node:fs";
import { join } from "node:path";

export default function NoisePage() {
  const rows = JSON.parse(
    readFileSync(join(process.cwd(), "fixtures/demo/noise.json"), "utf8"),
  ) as Array<Record<string, unknown>>;
  return (
    <main>
      <Banner title="NOISE is not queued" variant="warn">
        These rows were dropped at filter or dedupe. They are shown here with <code>_reason</code>{" "}
        for inspection only — never stored, listed, or messaged in production flow.
      </Banner>
      <PageHeader
        title="NOISE fixtures"
        description="Dropped candidates from the demo fixture set."
        meta={<Badge variant="neutral">{rows.length} rows</Badge>}
      />
      <Panel flush>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={String(r.id)}>
                  <td className="mono">{String(r.id)}</td>
                  <td>{String(r.name)}</td>
                  <td>
                    <span className="chip">{String(r._reason ?? "—")}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </main>
  );
}