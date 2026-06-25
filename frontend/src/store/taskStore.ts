import { create } from "zustand";
import type { TaskEvent } from "../types/api";

interface TaskState {
  currentTaskId: string | null;
  events: TaskEvent[];
  setCurrentTaskId: (taskId: string) => void;
  addEvent: (event: TaskEvent) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  currentTaskId: null,
  events: [],
  setCurrentTaskId: (taskId) => set({ currentTaskId: taskId }),
  addEvent: (event) =>
    set((state) => ({
      events: [event, ...state.events].slice(0, 50)
    }))
}));
