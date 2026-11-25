import { readFileSync } from "node:fs";
import { join } from "node:path";

export default function NoisePage() {
  const rows = JSON.parse(
    readFileSync(join(process.cwd(), "fixtures/demo/noise.json"), "utf8"),
  ) as Array<Record<string, unknown>>;
  return (
    <main>
      <h1>NOISE fixtures ({rows.length})</h1>
      <p className="muted">Dropped at filter/dedupe; listed here for demo only with _reason.</p>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>_reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.id)}>
              <td>{String(r.id)}</td>
              <td>{String(r.name)}</td>
              <td className="muted">{String(r._reason ?? "")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}