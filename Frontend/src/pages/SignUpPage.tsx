import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Calendar, Eye, EyeOff, ArrowRight, Loader2, Check } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const GoogleIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 24 24">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
);

const PasswordStrength: React.FC<{ password: string }> = ({ password }) => {
  const checks = [
    { label: '8+ characters', ok: password.length >= 8 },
    { label: 'Uppercase letter', ok: /[A-Z]/.test(password) },
    { label: 'Number', ok: /\d/.test(password) },
  ];
  const strength = checks.filter(c => c.ok).length;
  const colors = ['bg-red-500', 'bg-amber', 'bg-teal', 'bg-teal'];

  if (!password) return null;

  return (
    <div className="mt-2 space-y-2">
      <div className="flex gap-1">
        {[0, 1, 2].map(i => (
          <div key={i} className={`h-1 flex-1 rounded-full transition-all duration-300 ${i < strength ? colors[strength] : 'bg-border'}`} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {checks.map((c, i) => (
          <span key={i} className={`flex items-center gap-1 text-[11px] font-body transition-colors ${c.ok ? 'text-teal' : 'text-muted'}`}>
            <Check className="w-3 h-3" /> {c.label}
          </span>
        ))}
      </div>
    </div>
  );
};

const SignUpPage: React.FC = () => {
  const navigate = useNavigate();
  const { signUpWithEmail, signInWithGoogle, isLoading } = useAuth();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!agreed) { setError('Please accept the terms to continue.'); return; }
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    try {
      await signUpWithEmail(name, email, password);
      navigate('/dashboard');
    } catch {
      setError('Something went wrong. Please try again.');
    }
  };

  const handleGoogle = async () => {
    try {
      await signInWithGoogle();
      navigate('/dashboard');
    } catch {
      setError('Google sign-in failed. Please try again.');
    }
  };

  return (
    <div className="min-h-screen bg-ink grid-bg flex">
      {/* Left panel - decorative */}
      <div className="hidden lg:flex flex-col justify-between w-[420px] bg-surface border-r border-border p-10 relative overflow-hidden shrink-0">
        <div className="orb orb-accent w-80 h-80 -top-20 -left-20 opacity-40" />
        <div className="orb orb-teal w-64 h-64 -bottom-10 -right-10 opacity-30" />

        {/* Logo */}
        <button onClick={() => navigate('/')} className="flex items-center gap-2 relative z-10">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
            <Calendar className="w-4 h-4 text-white" />
          </div>
          <span className="font-display font-bold text-xl text-white">CalSync<span className="text-accent-glow">.ai</span></span>
        </button>

        {/* Testimonial */}
        <div className="relative z-10 space-y-6">
          <blockquote className="text-white font-body text-lg leading-relaxed">
            "I cc'd my CalSync address and it handled the entire scheduling thread automatically. Three participants, two timezones — booked in under 2 minutes."
          </blockquote>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-accent/30 flex items-center justify-center text-white font-semibold font-syne">SK</div>
            <div>
              <p className="text-white text-sm font-syne font-semibold">Siddharth Kumar</p>
              <p className="text-muted text-xs font-body">Engineering Manager, Bangalore</p>
            </div>
          </div>
        </div>

        {/* Perks */}
        <div className="relative z-10 space-y-3">
          {[
            'Free plan, no credit card needed',
            'Your dedicated @calsync.ai address',
            'Google Calendar connected instantly',
          ].map((perk, i) => (
            <div key={i} className="flex items-center gap-2.5 text-sm text-soft font-body">
              <div className="w-5 h-5 rounded-full bg-teal/15 flex items-center justify-center shrink-0">
                <Check className="w-3 h-3 text-teal" />
              </div>
              {perk}
            </div>
          ))}
        </div>
      </div>

      {/* Right panel - form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <button onClick={() => navigate('/')} className="flex items-center gap-2 mb-8 lg:hidden">
            <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
              <Calendar className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-display font-bold text-lg text-white">CalSync<span className="text-accent-glow">.ai</span></span>
          </button>

          <div className="mb-8">
            <h1 className="text-3xl font-display font-bold text-white">Create your account</h1>
            <p className="text-muted mt-2 font-body text-sm">Get your personal @calsync.ai address in seconds</p>
          </div>

          {/* Google button */}
          <button
            onClick={handleGoogle}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 bg-panel border border-border hover:border-white/20 text-soft hover:text-white py-3 rounded-xl transition-all duration-200 font-body text-sm mb-6 disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <GoogleIcon />}
            Continue with Google
          </button>

          <div className="flex items-center gap-4 mb-6">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs text-muted font-body">or with email</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">Full name</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Alex Johnson"
                className="input-field"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">Email address</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="alex@yourcompany.com"
                className="input-field"
                required
              />
              {email && (
                <p className="text-xs text-teal mt-1.5 font-body">
                  Your CalSync address: <span className="font-semibold">{email.split('@')[0].toLowerCase().replace(/[^a-z0-9]/g, '.')}@calsync.ai</span>
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Create a strong password"
                  className="input-field pr-11"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-soft"
                >
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <PasswordStrength password={password} />
            </div>

            {/* Terms */}
            <label className="flex items-start gap-3 cursor-pointer">
              <button
                type="button"
                onClick={() => setAgreed(!agreed)}
                className={`w-5 h-5 rounded border flex items-center justify-center shrink-0 mt-0.5 transition-all duration-200 ${
                  agreed ? 'bg-accent border-accent' : 'border-border bg-panel'
                }`}
              >
                {agreed && <Check className="w-3 h-3 text-white" />}
              </button>
              <span className="text-xs text-muted font-body leading-relaxed">
                I agree to the{' '}
                <a href="#" className="text-accent-glow hover:underline">Terms of Service</a>{' '}
                and{' '}
                <a href="#" className="text-accent-glow hover:underline">Privacy Policy</a>.
                I understand that outbound emails will include an AI disclaimer.
              </span>
            </label>

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
                <><Loader2 className="w-4 h-4 animate-spin" /> Setting up your account...</>
              ) : (
                <>Create account <ArrowRight className="w-4 h-4" /></>
              )}
            </button>
          </form>

          <p className="text-center text-sm text-muted mt-6 font-body">
            Already have an account?{' '}
            <Link to="/signin" className="text-accent-glow hover:underline font-medium">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default SignUpPage;
