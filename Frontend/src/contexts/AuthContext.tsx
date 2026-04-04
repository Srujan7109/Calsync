import React, { createContext, useContext, useState, useEffect } from 'react';

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  connectedEmail?: string;
  calSyncAddress?: string;
  plan: 'free' | 'pro';
  meetingsScheduled: number;
  hoursSaved: number;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (name: string, email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check for persisted session
    const stored = localStorage.getItem('calsync_user');
    if (stored) {
      setUser(JSON.parse(stored));
    }
    setIsLoading(false);
  }, []);

  const persistUser = (u: User) => {
    setUser(u);
    localStorage.setItem('calsync_user', JSON.stringify(u));
  };

  const signInWithGoogle = async () => {
    setIsLoading(true);
    // Simulate OAuth flow
    await new Promise(r => setTimeout(r, 1200));
    const mockUser: User = {
      id: 'google_' + Date.now(),
      name: 'Alex Johnson',
      email: 'alex.johnson@gmail.com',
      avatar: 'AJ',
      connectedEmail: 'alex.johnson@gmail.com',
      calSyncAddress: 'alex.j@calsync.ai',
      plan: 'free',
      meetingsScheduled: 0,
      hoursSaved: 0,
    };
    persistUser(mockUser);
    setIsLoading(false);
  };

  const signInWithEmail = async (email: string, _password: string) => {
    setIsLoading(true);
    await new Promise(r => setTimeout(r, 900));
    const name = email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    const initials = name.split(' ').map((n: string) => n[0]).join('').slice(0, 2);
    const slug = email.split('@')[0].toLowerCase().replace(/[^a-z0-9]/g, '.');
    const mockUser: User = {
      id: 'email_' + Date.now(),
      name,
      email,
      avatar: initials,
      connectedEmail: email,
      calSyncAddress: `${slug}@calsync.ai`,
      plan: 'free',
      meetingsScheduled: 12,
      hoursSaved: 4.5,
    };
    persistUser(mockUser);
    setIsLoading(false);
  };

  const signUpWithEmail = async (name: string, email: string, _password: string) => {
    setIsLoading(true);
    await new Promise(r => setTimeout(r, 1100));
    const initials = name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase();
    const slug = email.split('@')[0].toLowerCase().replace(/[^a-z0-9]/g, '.');
    const mockUser: User = {
      id: 'new_' + Date.now(),
      name,
      email,
      avatar: initials,
      connectedEmail: email,
      calSyncAddress: `${slug}@calsync.ai`,
      plan: 'free',
      meetingsScheduled: 0,
      hoursSaved: 0,
    };
    persistUser(mockUser);
    setIsLoading(false);
  };

  const signOut = () => {
    setUser(null);
    localStorage.removeItem('calsync_user');
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, signInWithGoogle, signInWithEmail, signUpWithEmail, signOut }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};
