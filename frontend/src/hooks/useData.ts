import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { Task } from "../lib/types";

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health });
}

export function useEvents() {
  return useQuery({ queryKey: ["events"], queryFn: api.events });
}

export function useTasks() {
  return useQuery({ queryKey: ["tasks"], queryFn: api.tasks });
}

export function useReminders() {
  return useQuery({ queryKey: ["reminders"], queryFn: api.reminders });
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

export function useToggleReminder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (r: { id: string; enabled: boolean }) =>
      api.updateReminder(r.id, { enabled: !r.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reminders"] }),
  });
}
