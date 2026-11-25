import { executeDemo } from "@/lib/demo-run";

export default function InvariantsPage() {
  const snap = executeDemo();
  const section0 = snap.section0.slice(0, 6);
  return (
    <main>
      <h1>Invariants</h1>
      <h2>Section 0 (six rows)</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Rule</th>
          </tr>
        </thead>
        <tbody>
          {section0.map((row) => (
            <tr key={row.id}>
              <td>{row.id}</td>
              <td>{row.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Demo run checks</h2>
      <table>
        <thead>
          <tr>
            <th>Check</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {snap.invariants.map((inv) => (
            <tr key={inv.name} className={inv.ok ? "pass" : "fail"}>
              <td>{inv.name}</td>
              <td>{inv.ok ? "PASS" : "FAIL"}</td>
              <td className="muted">{inv.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}