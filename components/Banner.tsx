type BannerVariant = "info" | "warn";

export function Banner({
  title,
  children,
  variant = "info",
}: {
  title: string;
  children: React.ReactNode;
  variant?: BannerVariant;
}) {
  return (
    <div className={`banner banner--${variant}`} role="status">
      <span className="banner__icon" aria-hidden />
      <div>
        <p className="banner__title">{title}</p>
        <p className="banner__text">{children}</p>
      </div>
    </div>
  );
}