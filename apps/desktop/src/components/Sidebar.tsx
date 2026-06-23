export type NavKey = "composer" | "design" | "library" | "docking" | "tools" | "settings";

const ITEMS: { key: NavKey; label: string; icon: string }[] = [
  { key: "composer", label: "Composer", icon: "✦" },
  { key: "design", label: "Design", icon: "✷" },
  { key: "library", label: "Library", icon: "▦" },
  { key: "docking", label: "Docking", icon: "⬡" },
  { key: "tools", label: "Tools", icon: "⚗" },
  { key: "settings", label: "Settings", icon: "⚙" },
];

export function Sidebar({
  active,
  onNavigate,
}: {
  active: NavKey;
  onNavigate: (key: NavKey) => void;
}) {
  return (
    <nav className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__logo" />
        <span className="sidebar__brandname">Glowsky</span>
      </div>
      {ITEMS.map((item) => (
        <button
          key={item.key}
          className={`navitem ${active === item.key ? "navitem--active" : ""}`}
          onClick={() => onNavigate(item.key)}
        >
          <span className="navitem__icon">{item.icon}</span>
          {item.label}
        </button>
      ))}
      <div className="sidebar__spacer" />
    </nav>
  );
}
