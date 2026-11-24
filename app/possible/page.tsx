import { executeDemo } from "@/lib/demo-run";

export default function PossiblePage() {
  const snap = executeDemo();
  return (
    <main>
      <h1>POSSIBLE ({snap.possible.length})</h1>
      <table>
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
                <td className="muted">{contact}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </main>
  );
}