import { createClient } from "@supabase/supabase-js";

type ViteEnv = {
  VITE_SUPABASE_URL?: string;
  VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY?: string;
};

const env = (import.meta as ImportMeta & { env: ViteEnv }).env;
const supabaseUrl = env.VITE_SUPABASE_URL;
const supabaseAnonKey = env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "Missing Supabase env vars: VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY",
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
