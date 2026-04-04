export interface Email {
  id: string;
  message_id: string;
  thread_id: string;
  from_email: string;
  subject: string;
  body_text: string;
  body_html?: string;
  received_at: string;
  is_processed: boolean;
  processing_status: "PENDING" | "PROCESSING" | "DONE" | "FAILED";
  session_id: string | null;
  labels: string[];
}

export interface Thread {
  thread_id: string;
  emails: Email[];
  count: number;
}
