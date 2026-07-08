import { create } from "zustand";
import type { TaskEvent } from "../types/api";

interface TaskState {
  currentTaskId: string | null;
  events: TaskEvent[];
  setCurrentTaskId: (taskId: string | null) => void;
  clearEvents: () => void;
  addEvent: (event: TaskEvent) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  currentTaskId: null,
  events: [],
  setCurrentTaskId: (taskId) => set({ currentTaskId: taskId }),
  clearEvents: () => set({ events: [] }),
  addEvent: (event) =>
    set((state) => ({
      events: [...state.events, event].slice(-50)
    }))
}));
