import { useState } from "react";

import { fmtTime } from "../lib/format";
import { Icon } from "../lib/icons";
import type { Task } from "../lib/types";

interface Props {
  tasks: Task[];
  onToggleTask: (t: Task) => void;
  onAddTask: (title: string) => Promise<unknown>;
}

function TaskRow({ task, onToggle }: { task: Task; onToggle: (t: Task) => void }) {
  return (
    <div className={"s-task" + (task.done ? " done" : "")} onClick={() => onToggle(task)}>
      <span className="s-check">
        <Icon name="tick" strokeWidth={3} />
      </span>
      <div className="s-task-x">
        <b>{task.title}</b>
        {task.due_at && <small>{fmtTime(task.due_at)}</small>}
      </div>
      {task.priority === "high" && <span className="s-prio hi">高</span>}
      {task.priority === "medium" && <span className="s-prio md">中</span>}
    </div>
  );
}

export function TasksView({ tasks, onToggleTask, onAddTask }: Props) {
  const [val, setVal] = useState("");
  const undone = tasks.filter((t) => !t.done);
  const done = tasks.filter((t) => t.done);

  const add = async () => {
    const v = val.trim();
    if (!v) return;
    try {
      await onAddTask(v);
      setVal(""); // 成功才清空，失敗則保留輸入（完整錯誤提示留待 M5）
    } catch {
      /* 保留輸入，待 M5 加上全域錯誤提示 */
    }
  };

  return (
    <div className="s-fadein" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="s-head">
        <div>
          <div className="s-eyebrow">任務</div>
          <h1 className="s-h1">待辦事項</h1>
          <div className="s-h-sub">
            {undone.length} 項待完成 · {done.length} 項已完成
          </div>
        </div>
        <div className="s-pills">
          <div className="s-pill">
            <b>{undone.length}</b>
            <small>進行中</small>
          </div>
          <div className="s-pill">
            <b>{Math.round((done.length / (tasks.length || 1)) * 100)}%</b>
            <small>完成率</small>
          </div>
        </div>
      </div>

      <div className="s-scroll">
        <div className="s-task-add">
          <span className="s-check" onClick={add} style={{ cursor: "pointer" }}>
            <Icon name="plus" strokeWidth={2.4} style={{ opacity: 1, color: "oklch(0.7 0.03 280)" }} />
          </span>
          <input
            value={val}
            placeholder="新增待辦事項，按 Enter 加入…"
            onChange={(e) => setVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") add();
            }}
          />
        </div>

        <div className="s-group-l">進行中</div>
        <div className="s-card">
          {undone.length ? (
            undone.map((t) => <TaskRow key={t.id} task={t} onToggle={onToggleTask} />)
          ) : (
            <div className="s-empty">全部完成了 🎉</div>
          )}
        </div>

        {done.length > 0 && (
          <>
            <div className="s-group-l">已完成</div>
            <div className="s-card" style={{ opacity: 0.85 }}>
              {done.map((t) => (
                <TaskRow key={t.id} task={t} onToggle={onToggleTask} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
