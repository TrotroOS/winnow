type StatItem = {
  label: string;
  value: string | number;
  hint?: string;
  accent?: boolean;
};

export function StatGrid({ items }: { items: StatItem[] }) {
  return (
    <div className="stat-grid" role="list">
      {items.map((item) => (
        <div
          key={item.label}
          className={`stat-card${item.accent ? " stat-card--accent" : ""}`}
          role="listitem"
        >
          <div className="stat-card__label">{item.label}</div>
          <div className="stat-card__value">{item.value}</div>
          {item.hint ? <div className="stat-card__hint">{item.hint}</div> : null}
        </div>
      ))}
    </div>
  );
}