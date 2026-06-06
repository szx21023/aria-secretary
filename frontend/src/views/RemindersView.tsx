import { REMINDER_META } from "../lib/categories";
import { fmtTime } from "../lib/format";
import { Icon } from "../lib/icons";
import type { Reminder } from "../lib/types";

interface Props {
  reminders: Reminder[];
  onToggleReminder: (r: Reminder) => void;
}

export function RemindersView({ reminders, onToggleReminder }: Props) {
  const activeCount = reminders.filter((r) => r.enabled).length;

  return (
    <div className="s-fadein" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="s-head">
        <div>
          <div className="s-eyebrow">提醒</div>
          <h1 className="s-h1">提醒與通知</h1>
          <div className="s-h-sub">{activeCount} 則啟用中</div>
        </div>
      </div>

      <div className="s-scroll">
        <div className="s-card">
          {reminders.map((r) => {
            const meta = REMINDER_META[r.kind];
            return (
              <div key={r.id} className="s-rem">
                <div
                  className="s-rem-ic"
                  style={{
                    background: `color-mix(in oklch, ${meta.tint} 22%, transparent)`,
                    color: meta.tint,
                  }}
                >
                  <Icon name={meta.icon} />
                </div>
                <div className="s-rem-x">
                  <b>{r.title}</b>
                  <small>{r.subtitle}</small>
                </div>
                {r.trigger_at && (
                  <span
                    className="s-mt-due"
                    style={{
                      marginRight: 6,
                      color: r.enabled ? "oklch(0.82 0.1 var(--acc1))" : "oklch(0.55 0.03 280)",
                    }}
                  >
                    {fmtTime(r.trigger_at)}
                  </span>
                )}
                <div
                  className={"s-tog" + (r.enabled ? " on" : "")}
                  onClick={() => onToggleReminder(r)}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
