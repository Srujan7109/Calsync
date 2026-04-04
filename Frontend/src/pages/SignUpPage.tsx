import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Calendar,
  Eye,
  EyeOff,
  ArrowRight,
  Loader2,
  Check,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

const PasswordStrength: React.FC<{ password: string }> = ({ password }) => {
  const checks = [
    { label: "8+ characters", ok: password.length >= 8 },
    { label: "Uppercase letter", ok: /[A-Z]/.test(password) },
    { label: "Number", ok: /\d/.test(password) },
  ];
  const strength = checks.filter((c) => c.ok).length;
  const colors = ["bg-red-500", "bg-amber", "bg-teal", "bg-teal"];

  if (!password) return null;

  return (
    <div className="mt-2 space-y-2">
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-all duration-300 ${i < strength ? colors[strength] : "bg-border"}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {checks.map((c, i) => (
          <span
            key={i}
            className={`flex items-center gap-1 text-[11px] font-body transition-colors ${c.ok ? "text-teal" : "text-muted"}`}
          >
            <Check className="w-3 h-3" /> {c.label}
          </span>
        ))}
      </div>
    </div>
  );
};

const SignUpPage: React.FC = () => {
  const navigate = useNavigate();
  const { signUpWithEmail, isLoading } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    try {
      await signUpWithEmail(name, email, password);
      navigate("/dashboard");
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.";
      setError(message);
    }
  };

  return (
    <div className="min-h-screen bg-ink grid-bg flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 mb-8"
        >
          <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
            <Calendar className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-display font-bold text-lg text-white">
            CalSync<span className="text-accent-glow">.ai</span>
          </span>
        </button>

        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold text-white">
            Create your account
          </h1>
          <p className="text-muted mt-2 font-body text-sm">
            Get your personal @calsync.ai address in seconds
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
              Full name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Alex Johnson"
              className="input-field"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
              Email address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="alex@yourcompany.com"
              className="input-field"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
              Password
            </label>
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Create a strong password"
                className="input-field pr-11"
                required
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-soft"
              >
                {showPw ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
              </button>
            </div>
            <PasswordStrength password={password} />
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-400 font-body">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="btn-primary w-full py-3.5 flex items-center justify-center gap-2 mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Setting up your
                account...
              </>
            ) : (
              <>
                Create account <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <p className="text-center text-sm text-muted mt-6 font-body">
          Already have an account?{" "}
          <Link
            to="/signin"
            className="text-accent-glow hover:underline font-medium"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
};

export default SignUpPage;
