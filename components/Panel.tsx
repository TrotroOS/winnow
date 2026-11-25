import type { ReactNode } from "react";

export function Panel({
  title,
  children,
  flush,
}: {
  title?: string;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className={`panel${flush ? " panel--flush" : ""}`}>
      {title ? (
        <div className="panel__body" style={{ paddingBottom: 0 }}>
          <h2 className="section-title">{title}</h2>
        </div>
      ) : null}
      <div className="panel__body">{children}</div>
    </section>
  );
}