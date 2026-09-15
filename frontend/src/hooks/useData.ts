import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { Task } from "../lib/types";

// 集中管理 React Query 的 query key，避免各處字串漂移導致靜默不刷新。
const QUERY_KEYS = {
  events: ["events"] as const,
  tasks: ["tasks"] as const,
  reminders: ["reminders"] as const,
  life: ["life"] as const,
};

export function useEvents() {
  return useQuery({ queryKey: QUERY_KEYS.events, queryFn: api.events });
}

export function useTasks() {
  return useQuery({ queryKey: QUERY_KEYS.tasks, queryFn: api.tasks });
}

export function useReminders() {
  return useQuery({ queryKey: QUERY_KEYS.reminders, queryFn: api.reminders });
}

export function useLife() {
  return useQuery({ queryKey: QUERY_KEYS.life, queryFn: api.life });
}

// ---- mutations ----

export function useAddTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title: string) => api.createTask({ title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.tasks }),
  });
}

export function useToggleTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (task: Task) => api.updateTask(task.id, { is_done: !task.is_done }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.tasks }),
  });
}

export function useSaveLife() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { birthday: string; life_expectancy: number }) => api.saveLife(body),
    onSuccess: (life) => qc.setQueryData(QUERY_KEYS.life, life),
  });
}

/** 新增里程碑等同新增一筆行程，人生頁與行事曆兩個 query 都要失效。 */
export function useAddMilestone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; target_date: string }) => api.createMilestone(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.life });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.events });
    },
  });
}

export function useToggleReminder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (r: { id: string; is_enabled: boolean }) =>
      api.updateReminder(r.id, { is_enabled: !r.is_enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.reminders }),
  });
}
