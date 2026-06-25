export interface ChatResponse {
  task_id: string;
  status: string;
}

export interface TaskEvent {
  event_id: string;
  task_id: string | null;
  type: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}
