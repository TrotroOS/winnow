import { Badge } from "@/components/Badge";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { executeDemo } from "@/lib/demo-run";

export default function BatchPage() {
  const snap = executeDemo();
  return (
    <main>
      <PageHeader
        title="Outreach batch"
        description="One message draft per POSSIBLE; send is gated on manual approve in this demo."
        meta={
          <>
            <Badge variant="accent">Batch {snap.batch.batchId}</Badge>
            <Badge variant="neutral">staged: {snap.outreach.skipped}</Badge>
          </>
        }
      />
      <Panel flush>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Channel</th>
                <th>Recipient</th>
              </tr>
            </thead>
            <tbody>
              {snap.batch.messages.map((m) => (
                <tr key={m.candidateId}>
                  <td className="mono">{m.candidateId}</td>
                  <td>
                    <span className="chip">{m.channel}</span>
                  </td>
                  <td className="muted mono">{m.recipient}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </main>
  );
}