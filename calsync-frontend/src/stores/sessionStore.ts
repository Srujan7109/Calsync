import { create } from "zustand";
import { Session } from "@/types/session";

interface SessionState {
  sessions: Session[];
  isLoading: boolean;
  setSessions: (sessions: Session[]) => void;
  updateSession: (updatedSession: Session) => void;
  setLoading: (loading: boolean) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  isLoading: true,
  setSessions: (sessions) => set({ sessions }),
  updateSession: (updatedSession) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.session_id === updatedSession.session_id ? updatedSession : s,
      ),
    })),
  setLoading: (isLoading) => set({ isLoading }),
}));
