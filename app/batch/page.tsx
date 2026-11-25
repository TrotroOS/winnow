import { executeDemo } from "@/lib/demo-run";

export default function BatchPage() {
  const snap = executeDemo();
  return (
    <main>
      <h1>Outreach batch</h1>
      <p className="muted">Batch {snap.batch.batchId} · manual approve · staged: {snap.outreach.skipped}</p>
      <table>
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
              <td>{m.candidateId}</td>
              <td>{m.channel}</td>
              <td className="muted">{m.recipient}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}