import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

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
