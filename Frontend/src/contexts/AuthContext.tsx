import React, { createContext, useContext, useState, useEffect } from "react";
import type { User as SupabaseUser } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  connectedEmail?: string;
  calSyncAddress?: string;
  plan: "free" | "pro";
  meetingsScheduled: number;
  hoursSaved: number;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (
    name: string,
    email: string,
    password: string,
  ) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const buildUserProfile = (authUser: SupabaseUser): User => {
    const email = authUser.email ?? "";
    const metadataName =
      typeof authUser.user_metadata?.full_name === "string"
        ? authUser.user_metadata.full_name
        : typeof authUser.user_metadata?.name === "string"
          ? authUser.user_metadata.name
          : null;

    const fallbackName = email
      ? email
          .split("@")[0]
          .replace(/[._]/g, " ")
          .replace(/\b\w/g, (l) => l.toUpperCase())
      : "User";

    const name = metadataName || fallbackName;
    const avatar = name
      .split(" ")
      .filter(Boolean)
      .map((n: string) => n[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
    const slug =
      email
        .split("@")[0]
        ?.toLowerCase()
        .replace(/[^a-z0-9]/g, ".") || "user";
    const plan = authUser.user_metadata?.plan === "pro" ? "pro" : "free";

    return {
      id: authUser.id,
      name,
      email,
      avatar,
      connectedEmail: email,
      calSyncAddress: `${slug}@calsync.ai`,
      plan,
      meetingsScheduled: 0,
      hoursSaved: 0,
    };
  };

  useEffect(() => {
    let mounted = true;

    const loadSession = async () => {
      const { data, error } = await supabase.auth.getSession();
      if (error) {
        console.error("Failed to load session", error.message);
      }

      if (!mounted) return;
      setUser(data.session?.user ? buildUserProfile(data.session.user) : null);
      setIsLoading(false);
    };

    loadSession();

    const { data: authListener } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ? buildUserProfile(session.user) : null);
        setIsLoading(false);
      },
    );

    return () => {
      mounted = false;
      authListener.subscription.unsubscribe();
    };
  }, []);

  const signInWithGoogle = async () => {
    setIsLoading(true);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/dashboard`,
      },
    });

    if (error) {
      setIsLoading(false);
      throw error;
    }
  };

  const signInWithEmail = async (email: string, password: string) => {
    setIsLoading(true);
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      setIsLoading(false);
      throw error;
    }

    setUser(data.user ? buildUserProfile(data.user) : null);
    setIsLoading(false);
  };

  const signUpWithEmail = async (
    name: string,
    email: string,
    password: string,
  ) => {
    setIsLoading(true);
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: name,
          name,
        },
      },
    });

    if (error) {
      setIsLoading(false);
      throw error;
    }

    if (!data.session) {
      setIsLoading(false);
      throw new Error(
        "Account created. Please verify your email before signing in.",
      );
    }

    setUser(data.user ? buildUserProfile(data.user) : null);
    setIsLoading(false);
  };

  const signOut = async () => {
    setIsLoading(true);
    const { error } = await supabase.auth.signOut();
    setUser(null);

    if (error) {
      setIsLoading(false);
      throw error;
    }

    setIsLoading(false);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        signInWithGoogle,
        signInWithEmail,
        signUpWithEmail,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
