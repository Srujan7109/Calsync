import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Calendar, Eye, EyeOff, ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

const SignInPage: React.FC = () => {
  const navigate = useNavigate();
  const { signInWithEmail, isLoading } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await signInWithEmail(email, password);
      navigate("/dashboard");
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Invalid email or password. Please try again.";
      setError(message);
    }
  };

  return (
    <div className="min-h-screen bg-ink grid-bg flex items-center justify-center p-6">
      {/* Background orbs */}
      <div className="orb orb-accent w-[500px] h-[500px] top-0 right-0 opacity-20 fixed pointer-events-none" />
      <div className="orb orb-teal w-[400px] h-[400px] bottom-0 left-0 opacity-15 fixed pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        {/* Logo */}
        <div className="text-center mb-10">
          <button
            onClick={() => navigate("/")}
            className="inline-flex items-center gap-2 mb-6"
          >
            <div className="w-9 h-9 rounded-xl bg-accent flex items-center justify-center">
              <Calendar className="w-5 h-5 text-white" />
            </div>
            <span className="font-display font-bold text-2xl text-white">
              CalSync<span className="text-accent-glow">.ai</span>
            </span>
          </button>
          <h1 className="text-3xl font-display font-bold text-white">
            Welcome back
          </h1>
          <p className="text-muted mt-2 font-body text-sm">
            Sign in to your scheduling assistant
          </p>
        </div>

        {/* Card */}
        <div className="glass rounded-2xl p-8">
          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="input-field"
                required
                autoComplete="email"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider">
                  Password
                </label>
                <a
                  href="#"
                  className="text-xs text-accent-glow hover:underline font-body"
                >
                  Forgot password?
                </a>
              </div>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Your password"
                  className="input-field pr-11"
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-soft transition-colors"
                >
                  {showPw ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-400 font-body">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="btn-primary w-full py-3.5 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Signing in...
                </>
              ) : (
                <>
                  Sign in <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-muted mt-6 font-body">
          Don't have an account?{" "}
          <Link
            to="/signup"
            className="text-accent-glow hover:underline font-medium"
          >
            Create one free
          </Link>
        </p>
      </div>
    </div>
  );
};

export default SignInPage;
