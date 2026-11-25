type BadgeVariant = "pass" | "fail" | "neutral" | "accent";

export function Badge({
  children,
  variant = "neutral",
}: {
  children: React.ReactNode;
  variant?: BadgeVariant;
}) {
  return <span className={`badge badge--${variant}`}>{children}</span>;
}