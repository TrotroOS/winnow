import { Badge } from "@/components/Badge";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { executeDemo } from "@/lib/demo-run";

export default function InvariantsPage() {
  const snap = executeDemo();
  const section0 = snap.section0.slice(0, 6);
  const allPass = snap.invariants.every((i) => i.ok);
  return (
    <main>
      <PageHeader
        title="Invariants"
        description="Section 0 rules and automated checks for this fixture run."
        meta={
          <Badge variant={allPass ? "pass" : "fail"}>{allPass ? "All checks pass" : "Failures present"}</Badge>
        }
      />
      <Panel title="Section 0 (six rows)" flush>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Rule</th>
              </tr>
            </thead>
            <tbody>
              {section0.map((row) => (
                <tr key={row.id}>
                  <td className="mono">{row.id}</td>
                  <td>{row.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel title="Demo run checks" flush>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Check</th>
                <th>Status</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {snap.invariants.map((inv) => (
                <tr key={inv.name} className={inv.ok ? "row-pass" : "row-fail"}>
                  <td className="mono">{inv.name}</td>
                  <td>
                    <Badge variant={inv.ok ? "pass" : "fail"}>{inv.ok ? "PASS" : "FAIL"}</Badge>
                  </td>
                  <td className="muted">{inv.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </main>
  );
}