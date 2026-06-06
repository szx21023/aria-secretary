// M0 佔位視圖。M2 會用真正的 TodayView / CalendarView / TasksView / RemindersView 取代。

interface PlaceholderProps {
  eyebrow: string;
  title: string;
  subtitle: string;
}

export function Placeholder({ eyebrow, title, subtitle }: PlaceholderProps) {
  return (
    <div className="s-fadein">
      <div className="s-head">
        <div>
          <div className="s-eyebrow">{eyebrow}</div>
          <h1 className="s-h1">{title}</h1>
          <div className="s-h-sub">{subtitle}</div>
        </div>
      </div>
      <div className="s-scroll">
        <div className="s-card">
          <div className="s-empty">M0 骨架就緒 — 此視圖將於 M2 完成移植 ✨</div>
        </div>
      </div>
    </div>
  );
}
