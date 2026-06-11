import { useChatContext } from "../hooks/ChatContext";
import { CAT } from "../lib/categories";
import { durationMin, fmtHours, fmtMonthDay, fmtTime } from "../lib/format";
import { Icon } from "../lib/icons";
import type { Event } from "../lib/types";

interface Props {
  ev: Event;
  onClose: () => void;
}

export function EventDetail({ ev, onClose }: Props) {
  const { send, thinking } = useChatContext();
  const c = CAT[ev.category];
  const mins = durationMin(ev.start_at, ev.end_at);

  // 把行程資訊組成一句自然語言丟進對話，秘書再追問要改到何時（同原型體驗）。
  // 帶上日期＋時間，避免同名行程被改錯。
  const askReschedule = () => {
    const when = `${fmtMonthDay(new Date(ev.start_at))} ${fmtTime(ev.start_at)}`;
    send(`請幫我把「${ev.title}」（${when}）改期`);
    onClose();
  };

  return (
    <div className="s-pop-back" onClick={onClose}>
      <div className="s-pop s-fadein" onClick={(e) => e.stopPropagation()}>
        <div className="s-pop-x" onClick={onClose}>
          <Icon name="x" />
        </div>
        <span
          className="s-cat-chip"
          style={{ background: `color-mix(in oklch, ${c.color} 22%, transparent)`, color: c.color }}
        >
          <span className="s-cat-chip-dot" style={{ background: c.color }} />
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
          <button
            className="s-btn primary"
            onClick={askReschedule}
            disabled={thinking}
            title={thinking ? "秘書正在處理上一則訊息…" : "送進對話請秘書改期"}
          >
            請秘書改期
          </button>
        </div>
      </div>
    </div>
  );
}
