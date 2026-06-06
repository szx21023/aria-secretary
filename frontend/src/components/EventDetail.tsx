import { CAT } from "../lib/categories";
import { durationMin, fmtHours, fmtTime } from "../lib/format";
import { Icon } from "../lib/icons";
import type { Event } from "../lib/types";

interface Props {
  ev: Event;
  onClose: () => void;
}

export function EventDetail({ ev, onClose }: Props) {
  const c = CAT[ev.category];
  const mins = durationMin(ev.start_at, ev.end_at);

  return (
    <div className="s-pop-back" onClick={onClose}>
      <div className="s-pop s-fadein" onClick={(e) => e.stopPropagation()}>
        <div className="s-pop-x" onClick={onClose}>
          <Icon name="x" />
        </div>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 12.5,
            padding: "5px 12px",
            borderRadius: 999,
            background: `color-mix(in oklch, ${c.color} 22%, transparent)`,
            color: c.color,
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.color }} />
          {c.label}
        </span>
        <h3>{ev.title}</h3>
        <div className="s-pop-meta">
          <div className="row">
            <Icon name="clock" />
            {fmtTime(ev.start_at)} – {fmtTime(ev.end_at)}（{fmtHours(mins)}）
          </div>
          <div className="row">
            <Icon name="pin" />
            {ev.location}
          </div>
          {ev.attendees && (
            <div className="row">
              <Icon name="users" />
              {ev.attendees} 位參與者
            </div>
          )}
          {ev.note && (
            <div className="row">
              <Icon name="sparkle" />
              {ev.note}
            </div>
          )}
        </div>
        <div className="s-pop-actions">
          <button className="s-btn" onClick={onClose}>
            關閉
          </button>
          {/* M3 接上 AI 後改為「請秘書改期」送進對話 */}
          <button className="s-btn primary" disabled title="AI 對話將於 M3 啟用">
            請秘書改期
          </button>
        </div>
      </div>
    </div>
  );
}
