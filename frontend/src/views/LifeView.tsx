import { useState } from "react";

import { Icon } from "../lib/icons";
import type { Life, LifeStats, Milestone } from "../lib/types";

interface Props {
  life: Life | undefined;
  onSave: (body: { birthday: string; life_expectancy: number }) => Promise<unknown>;
  saving: boolean;
  onAddMilestone: (body: { title: string; target_date: string }) => Promise<unknown>;
  /** 人生頁不參與整頁 loading 閘門，錯誤得自己顯示，否則失敗會停在「載入中…」。 */
  error?: boolean;
}

const MIN_EXPECTANCY = 1;
const MAX_EXPECTANCY = 150;

const num = (n: number) => n.toLocaleString("zh-TW");

/** 後端的 `YYYY-MM-DD` → 「1990 / 03 / 14」。不經 Date，避免時區位移。 */
const fmtISODate = (iso: string) => iso.split("-").join(" / ");

function StatCard({
  label,
  value,
  unit,
  hint,
}: {
  label: string;
  value: string;
  unit: string;
  hint?: string;
}) {
  return (
    <div className="s-life-stat">
      <div className="s-life-stat-l">{label}</div>
      <div className="s-life-stat-v s-mono">
        {value}
        <span>{unit}</span>
      </div>
      {hint && <div className="s-life-stat-h">{hint}</div>}
    </div>
  );
}

/** 設定／調整基準資料。生日與預期壽命皆為必填，送出前先在前端擋掉明顯無效值。 */
function LifeForm({
  life,
  onSave,
  saving,
  onCancel,
}: {
  life: Life;
  onSave: Props["onSave"];
  saving: boolean;
  onCancel?: () => void;
}) {
  const [birthday, setBirthday] = useState(life.birthday ?? "");
  const [expectancy, setExpectancy] = useState(String(life.life_expectancy));
  const [err, setErr] = useState("");

  const today = new Date();
  const todayISO = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(
    today.getDate(),
  ).padStart(2, "0")}`;

  const submit = async () => {
    const years = Number(expectancy);
    if (!birthday) return setErr("請填生日");
    if (birthday > todayISO) return setErr("生日不能是未來的日期");
    if (!Number.isInteger(years) || years < MIN_EXPECTANCY || years > MAX_EXPECTANCY) {
      return setErr(`預期壽命需為 ${MIN_EXPECTANCY}–${MAX_EXPECTANCY} 的整數`);
    }
    setErr("");
    try {
      await onSave({ birthday, life_expectancy: years });
      onCancel?.();
    } catch {
      setErr("儲存失敗，請確認後端是否正常");
    }
  };

  return (
    <div className="s-card s-life-form">
      <div className="s-eyebrow">基準設定</div>
      <div className="s-life-fields">
        <label>
          <span>生日</span>
          <input
            type="date"
            max={todayISO}
            value={birthday}
            onChange={(e) => setBirthday(e.target.value)}
          />
        </label>
        <label>
          <span>預期壽命（歲）</span>
          <input
            type="number"
            min={MIN_EXPECTANCY}
            max={MAX_EXPECTANCY}
            value={expectancy}
            onChange={(e) => setExpectancy(e.target.value)}
          />
        </label>
      </div>
      {err && <div className="s-life-err">{err}</div>}
      <div className="s-pop-actions">
        {onCancel && (
          <button className="s-btn" onClick={onCancel} disabled={saving}>
            取消
          </button>
        )}
        <button className="s-btn primary" onClick={submit} disabled={saving}>
          {saving ? "儲存中…" : "儲存"}
        </button>
      </div>
    </div>
  );
}

function MilestoneRow({ m }: { m: Milestone }) {
  const meta = [fmtISODate(m.target_date), m.age_at !== null ? `屆時 ${m.age_at} 歲` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="s-ms">
      <div className="s-ms-x">
        <div className="s-ms-t">
          <b>{m.title}</b>
          <div className="s-ms-d s-mono">
            {m.days_left === 0 ? (
              <em>就是今天</em>
            ) : (
              <>
                {num(m.days_left)}
                <span>天</span>
              </>
            )}
          </div>
        </div>
        {/* 進度以「行程建立那天」為起點，與生命餘額的已過/總天數同一個讀法 */}
        <div className="s-ms-p">
          <small>{meta}</small>
          <div className="s-life-bar s-ms-bar">
            <div className="s-life-fill" style={{ width: `${m.percent_elapsed}%` }} />
          </div>
          <small className="s-mono">
            {num(m.elapsed_days)} / {num(m.total_days)} 天
          </small>
        </div>
      </div>
    </div>
  );
}

/** 重大目標／事件的倒數。里程碑就是標了 is_milestone 的行程，故新增等同新增一筆行程。 */
function Milestones({
  milestones,
  onAdd,
}: {
  milestones: Milestone[];
  onAdd: Props["onAddMilestone"];
}) {
  const [title, setTitle] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [err, setErr] = useState("");

  const add = async () => {
    const t = title.trim();
    if (!t || !targetDate) return setErr("目標名稱與日期都要填");
    setErr("");
    try {
      await onAdd({ title: t, target_date: targetDate });
      setTitle("");
      setTargetDate("");
    } catch {
      setErr("新增失敗，請確認後端是否正常");
    }
  };

  return (
    <>
      <div className="s-group-l">重大目標</div>
      <div className="s-card">
        {milestones.length ? (
          milestones.map((m) => <MilestoneRow key={m.id} m={m} />)
        ) : (
          <div className="s-empty">還沒有標記任何里程碑 — 在下面加一個，或直接跟秘書說</div>
        )}
      </div>

      <div className="s-task-add s-ms-add">
        <span className="s-check" onClick={add} style={{ cursor: "pointer" }}>
          <Icon
            name="plus"
            strokeWidth={2.4}
            style={{ opacity: 1, color: "oklch(0.7 0.03 280)" }}
          />
        </span>
        <input
          value={title}
          placeholder="新增重大目標，例如「考完證照」…"
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") add();
          }}
        />
        <input
          className="s-ms-date"
          type="date"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
        />
      </div>
      {err && <div className="s-life-err">{err}</div>}
    </>
  );
}

function LifeHero({ stats }: { stats: LifeStats }) {
  return (
    <div className="s-card s-life-hero">
      <div className="s-life-hero-l">生命餘額</div>
      <div className="s-life-num s-mono">
        {num(stats.remaining_days)}
        <span>天</span>
      </div>
      <div className="s-life-bar">
        <div className="s-life-fill" style={{ width: `${stats.percent_lived}%` }} />
      </div>
      <div className="s-life-bar-x">
        <span>已過 {stats.percent_lived}%</span>
        <span className="s-mono">
          {num(stats.lived_days)} / {num(stats.total_days)} 天
        </span>
      </div>
    </div>
  );
}

function LifeBreakdown({ stats }: { stats: LifeStats }) {
  return (
    <>
      <div className="s-group-l">換算</div>
      <div className="s-life-grid">
        <StatCard label="剩餘週數" value={num(stats.remaining_weeks)} unit="週" />
        <StatCard label="剩餘年數" value={num(stats.remaining_years)} unit="年" />
        <StatCard
          label="已活過"
          value={num(stats.lived_days)}
          unit="天"
          hint={`${num(stats.lived_weeks)} 週`}
        />
      </div>

      <div className="s-group-l">近期</div>
      <div className="s-life-grid">
        <StatCard label="今年剩" value={num(stats.days_left_this_year)} unit="天" />
        <StatCard label="本月剩" value={num(stats.days_left_this_month)} unit="天" />
        <StatCard
          label="距離生日"
          value={num(stats.next_birthday_in_days)}
          unit="天"
          hint={stats.next_birthday_in_days === 0 ? "就是今天 🎂" : undefined}
        />
      </div>
    </>
  );
}

export function LifeView({ life, onSave, saving, onAddMilestone, error }: Props) {
  const [editing, setEditing] = useState(false);

  if (!life) {
    return (
      <div className="s-fadein">
        <div className="s-card">
          <div className="s-empty">
            {error ? "無法連線後端 — 請確認 API 是否啟動於 :8000" : "載入中…"}
          </div>
        </div>
      </div>
    );
  }

  const stats = life.stats;

  return (
    <div className="s-fadein" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="s-head">
        <div>
          <div className="s-eyebrow">人生</div>
          <h1 className="s-h1">人生倒數行事曆</h1>
          <div className="s-h-sub">
            {stats
              ? `${fmtISODate(life.birthday!)} 生 · ${stats.age} 歲 · 預期 ${life.life_expectancy} 歲（至 ${fmtISODate(
                  stats.end_date,
                )}）`
              : "設定生日與預期壽命，開始倒數"}
          </div>
        </div>
        {stats && (
          <div className="s-pills">
            <div className="s-pill">
              <b className="s-mono">{stats.percent_lived}%</b>
              <small>已過</small>
            </div>
            <div className="s-pill">
              <b className="s-mono">{num(stats.remaining_weeks)}</b>
              <small>剩餘週數</small>
            </div>
            <div className="s-ni s-life-edit" onClick={() => setEditing((v) => !v)}>
              <Icon name="settings" />
              <span className="s-tip">調整基準</span>
            </div>
          </div>
        )}
      </div>

      <div className="s-scroll">
        {stats && <LifeHero stats={stats} />}
        <Milestones milestones={life.milestones} onAdd={onAddMilestone} />
        {stats && <LifeBreakdown stats={stats} />}
        {(!stats || editing) && (
          <LifeForm
            life={life}
            onSave={onSave}
            saving={saving}
            onCancel={stats ? () => setEditing(false) : undefined}
          />
        )}
      </div>
    </div>
  );
}
