import { executeDemo } from "@/lib/demo-run";

export default function HomePage() {
  const snap = executeDemo();
  return (
    <main>
      <h1>Winnow mock demo</h1>
      <p className="muted">Template: {snap.templateName}</p>
      <p>
        <strong>{snap.possible.length}</strong> POSSIBLE · noise dropped{" "}
        <strong>{snap.noiseDropped}</strong> · dedupe dropped{" "}
        <strong>{snap.dedupeDropped}</strong>
      </p>
      <p className="muted">Filter now: {snap.filterNow}</p>
      <h2>Situation</h2>
      <ul className="muted">
        <li>Segment: {snap.situation.segment}</li>
        <li>Product: {snap.situation.product}</li>
        <li>Goal: {snap.situation.goal}</li>
        <li>Criteria: {snap.criteriaNames.join(", ")}</li>
      </ul>
      <h2>Message preview (first POSSIBLE)</h2>
      <pre className="muted">{snap.preview || "(none)"}</pre>
    </main>
  );
}