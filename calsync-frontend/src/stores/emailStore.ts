import { create } from "zustand";
import { Email } from "@/types/email";

interface EmailState {
  emails: Email[];
  isLoading: boolean;
  setEmails: (emails: Email[]) => void;
  addEmail: (email: Email) => void;
  setLoading: (loading: boolean) => void;
}

export const useEmailStore = create<EmailState>((set) => ({
  emails: [],
  isLoading: true,
  setEmails: (emails) => set({ emails }),
  addEmail: (email) => set((state) => ({ emails: [email, ...state.emails] })),
  setLoading: (isLoading) => set({ isLoading }),
}));
