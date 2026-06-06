import { Icon } from "../lib/icons";

export type ViewId = "today" | "calendar" | "tasks" | "reminders";

const NAV: { id: ViewId; icon: string; label: string }[] = [
  { id: "today", icon: "home", label: "今日" },
  { id: "calendar", icon: "calendar", label: "行事曆" },
  { id: "tasks", icon: "check", label: "任務" },
  { id: "reminders", icon: "bell", label: "提醒" },
];

interface NavProps {
  view: ViewId;
  onChange: (v: ViewId) => void;
  reminderCount?: number;
}

export function Nav({ view, onChange, reminderCount = 0 }: NavProps) {
  return (
    <nav className="s-nav">
      <div className="s-logo">A</div>
      <div className="s-navset">
        {NAV.map((n) => (
          <div
            key={n.id}
            className={"s-ni" + (view === n.id ? " on" : "")}
            onClick={() => onChange(n.id)}
          >
            <Icon name={n.icon} />
            {n.id === "reminders" && reminderCount > 0 && (
              <span className="s-badge">{reminderCount}</span>
            )}
            <span className="s-tip">{n.label}</span>
          </div>
        ))}
      </div>
      <div className="s-nav-sp" />
      <div className="s-ni">
        <Icon name="settings" />
        <span className="s-tip">設定</span>
      </div>
      <div className="s-av">CL</div>
    </nav>
  );
}
