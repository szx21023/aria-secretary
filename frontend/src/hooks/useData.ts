import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { Task } from "../lib/types";

export function useEvents() {
  return useQuery({ queryKey: ["events"], queryFn: api.events });
}

export function useTasks() {
  return useQuery({ queryKey: ["tasks"], queryFn: api.tasks });
}

export function useReminders() {
  return useQuery({ queryKey: ["reminders"], queryFn: api.reminders });
}

export function useLife() {
  return useQuery({ queryKey: ["life"], queryFn: api.life });
}

// ---- mutations ----

export function useAddTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title: string) => api.createTask({ title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useToggleTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (task: Task) => api.updateTask(task.id, { done: !task.done }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useSaveLife() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { birthday: string; life_expectancy: number }) => api.saveLife(body),
    onSuccess: (life) => qc.setQueryData(["life"], life),
  });
}

/** 新增里程碑等同新增一筆行程，人生頁與行事曆兩個 query 都要失效。 */
export function useAddMilestone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; target_date: string }) => api.createMilestone(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["life"] });
      qc.invalidateQueries({ queryKey: ["events"] });
    },
  });
}

export function useToggleReminder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (r: { id: string; enabled: boolean }) =>
      api.updateReminder(r.id, { enabled: !r.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reminders"] }),
  });
}
