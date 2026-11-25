import { Badge } from "@/components/Badge";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { executeDemo } from "@/lib/demo-run";

export default function PossiblePage() {
  const snap = executeDemo();
  return (
    <main>
      <PageHeader
        title="POSSIBLE survivors"
        description="Candidates that passed reachability and all predicates at filter time."
        meta={<Badge variant="accent">{snap.possible.length} listed</Badge>}
      />
      <Panel flush>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Org</th>
                <th>Role</th>
                <th>Contact</th>
              </tr>
            </thead>
            <tbody>
              {snap.possible.map((c) => {
                const contacts = c.contacts as Record<string, string>;
                const contact =
                  contacts.email || contacts.linkedin || contacts.dm || "";
                return (
                  <tr key={String(c.id)}>
                    <td>{String(c.name)}</td>
                    <td>{String(c.org)}</td>
                    <td>{String(c.role)}</td>
                    <td className="muted mono">{contact}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </main>
  );
}