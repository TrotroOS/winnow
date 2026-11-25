import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: string;
  meta?: ReactNode;
};

export function PageHeader({ title, description, meta }: PageHeaderProps) {
  return (
    <header className="page-header">
      <h1>{title}</h1>
      {description ? <p className="page-header__desc">{description}</p> : null}
      {meta ? <div className="page-header__meta">{meta}</div> : null}
    </header>
  );
}