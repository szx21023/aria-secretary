// 對應後端 Pydantic schema。datetime 為帶 offset 的 ISO 字串（UTC）。

export type EventCategory = "meeting" | "focus" | "meal" | "personal";
export type EventStatus = "scheduled" | "live" | "done";
export type TaskPriority = "high" | "medium" | "low";
export type ReminderKind = "meeting" | "birthday" | "bill" | "health";

export interface Event {
  id: string;
  title: string;
  start_at: string;
  end_at: string;
  category: EventCategory;
  location: string | null;
  attendees: number | null;
  status: EventStatus;
  note: string | null;
  /** 標為人生里程碑：行事曆照常顯示，人生倒數頁只挑有標記的算倒數。 */
  is_milestone: boolean;
}

export interface Task {
  id: string;
  title: string;
  due_at: string | null;
  priority: TaskPriority | null;
  done: boolean;
}

export interface Reminder {
  id: string;
  title: string;
  subtitle: string | null;
  trigger_at: string | null;
  recurrence: string | null;
  kind: ReminderKind;
  enabled: boolean;
}

/** 人生倒數的推導數字。日期為 `YYYY-MM-DD`（後端以 APP_TZ 的「今天」為基準）。 */
export interface LifeStats {
  today: string;
  end_date: string;
  age: number;
  total_days: number;
  lived_days: number;
  remaining_days: number;
  percent_lived: number;
  lived_weeks: number;
  remaining_weeks: number;
  remaining_years: number;
  days_left_this_year: number;
  days_left_this_month: number;
  next_birthday_in_days: number;
}

/** 標為里程碑的未來行程，附後端算好的倒數。 */
export interface Milestone {
  id: string;
  title: string;
  start_at: string;
  target_date: string;
  days_left: number;
  /** 進度的起算點：這筆里程碑被建立的日期。 */
  created_date: string;
  /** 進度分母＝目標日−建立日；分子＝今天−建立日。 */
  total_days: number;
  elapsed_days: number;
  percent_elapsed: number;
  /** 屆時歲數；未設定生日則為 null。 */
  age_at: number | null;
  category: EventCategory;
  location: string | null;
  note: string | null;
}

/** 尚未設定生日時 birthday 與 stats 為 null；milestones 與生日無關，一律附上。 */
export interface Life {
  birthday: string | null;
  life_expectancy: number;
  stats: LifeStats | null;
  milestones: Milestone[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
}
