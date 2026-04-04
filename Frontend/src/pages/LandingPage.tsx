import React, { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mail, Calendar, Clock, Zap, Shield, Globe,
  ArrowRight, Check, Star, Users, Cpu, ChevronRight,
  Sparkles, BarChart2, RefreshCw, MessageSquare
} from 'lucide-react';
import Navbar from '../components/Navbar';

// ── Animated counter hook ──
const useCounter = (target: number, duration = 2000, start = false) => {
  const [count, setCount] = React.useState(0);
  useEffect(() => {
    if (!start) return;
    let startTime: number;
    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      setCount(Math.floor(progress * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration, start]);
  return count;
};

// ── Intersection Observer hook ──
const useInView = (threshold = 0.1) => {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = React.useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setInView(true); }, { threshold });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, inView };
};

// ── EmailDemo animation ──
const EmailDemo: React.FC = () => {
  const [step, setStep] = React.useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep(s => (s + 1) % 5), 2000);
    return () => clearInterval(id);
  }, []);

  const emails = [
    { from: 'sarah@acme.com', subject: 'Q3 sync — I\'m free Mon 2-4pm or Wed anytime', time: '10:32 AM', tag: 'Incoming' },
    { from: 'calsync processing...', subject: 'Parsing: Mon 2-4pm, Wed all day', time: '10:32 AM', tag: 'Analyzing', accent: true },
    { from: 'mike@startup.io', subject: 'Works for me! Tuesday 3pm is good too', time: '10:34 AM', tag: 'Reply' },
    { from: 'ai@calsync.ai', subject: 'Overlap found: Wed 2-3pm ✓ Booking now', time: '10:34 AM', tag: 'AI Action', teal: true },
    { from: 'calendar@google.com', subject: '📅 Invite sent — Q3 Sync, Wed 2 PM confirmed', time: '10:34 AM', tag: 'Done', success: true },
  ];

  return (
    <div className="glass rounded-2xl overflow-hidden w-full max-w-md">
      {/* Window chrome */}
      <div className="flex items-center gap-2 px-4 py-3 bg-panel border-b border-border">
        <div className="w-3 h-3 rounded-full bg-red-500/60" />
        <div className="w-3 h-3 rounded-full bg-amber/60" />
        <div className="w-3 h-3 rounded-full bg-teal/60" />
        <span className="ml-3 text-xs text-muted font-body">Inbox — CalSync.ai</span>
      </div>
      {/* Email list */}
      <div className="divide-y divide-border">
        {emails.map((email, i) => (
          <div
            key={i}
            className={`px-4 py-3 transition-all duration-500 ${
              i === step
                ? email.teal ? 'bg-teal/5 border-l-2 border-teal'
                  : email.success ? 'bg-green-500/5 border-l-2 border-green-500'
                  : email.accent ? 'bg-accent/5 border-l-2 border-accent'
                  : 'bg-white/3 border-l-2 border-white/20'
                : 'opacity-40'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-semibold truncate font-syne ${
                  email.accent ? 'text-accent-glow' : email.teal ? 'text-teal' : email.success ? 'text-green-400' : 'text-soft'
                }`}>
                  {email.from}
                </p>
                <p className="text-xs text-muted mt-0.5 truncate font-body">{email.subject}</p>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <span className="text-[10px] text-muted font-body">{email.time}</span>
                <span className={`text-[9px] px-1.5 py-0.5 rounded font-syne font-semibold ${
                  email.teal ? 'bg-teal/15 text-teal'
                    : email.success ? 'bg-green-500/15 text-green-400'
                    : email.accent ? 'bg-accent/15 text-accent-glow'
                    : 'bg-white/10 text-soft'
                }`}>
                  {email.tag}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Stats section ──
const StatsSection: React.FC = () => {
  const { ref, inView } = useInView();
  const hours = useCounter(3, 1800, inView);
  const meetings = useCounter(847, 2000, inView);
  const reduction = useCounter(80, 1500, inView);

  return (
    <div ref={ref} className="grid grid-cols-1 md:grid-cols-3 gap-px bg-border rounded-2xl overflow-hidden">
      {[
        { value: `${hours}–5`, suffix: 'hrs/week saved', label: 'Per professional, on average' },
        { value: meetings.toLocaleString(), suffix: '+', label: 'Meetings auto-scheduled daily' },
        { value: reduction, suffix: '%', label: 'Reduction in scheduling overhead' },
      ].map((stat, i) => (
        <div key={i} className="bg-surface px-8 py-10 text-center">
          <div className="text-4xl font-display font-bold text-white">
            {stat.value}<span className="text-accent-glow">{stat.suffix}</span>
          </div>
          <div className="text-sm text-muted mt-2 font-body">{stat.label}</div>
        </div>
      ))}
    </div>
  );
};

// ── Feature card ──
interface FeatureCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  tag?: string;
  accent?: boolean;
}
const FeatureCard: React.FC<FeatureCardProps> = ({ icon, title, description, tag, accent }) => (
  <div className={`group relative rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 border ${
    accent
      ? 'bg-accent/5 border-accent/20 hover:border-accent/40'
      : 'bg-panel border-border hover:border-border'
  }`}
  style={{ boxShadow: accent ? '0 0 40px rgba(91,91,214,0.08)' : undefined }}>
    {tag && (
      <span className="absolute top-4 right-4 text-[10px] font-syne font-semibold px-2 py-0.5 rounded-full bg-teal/15 text-teal">
        {tag}
      </span>
    )}
    <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${
      accent ? 'bg-accent/20' : 'bg-border'
    }`}>
      <span className={accent ? 'text-accent-glow' : 'text-soft'}>{icon}</span>
    </div>
    <h3 className="font-syne font-semibold text-white text-base mb-2">{title}</h3>
    <p className="text-sm text-muted font-body leading-relaxed">{description}</p>
  </div>
);

// ── Ticker ──
const Ticker: React.FC = () => {
  const items = [
    '✦ Zero back-and-forth', '✦ Works via email', '✦ Google Calendar sync',
    '✦ Multi-timezone aware', '✦ AI-powered NLP', '✦ No new apps needed',
    '✦ Duplicate-safe booking', '✦ Priority scheduling', '✦ Instant confirmations',
  ];
  const doubled = [...items, ...items];
  return (
    <div className="overflow-hidden border-y border-border py-4 bg-surface/50">
      <div className="flex animate-marquee whitespace-nowrap">
        {doubled.map((item, i) => (
          <span key={i} className="mx-8 text-sm text-muted font-body shrink-0">{item}</span>
        ))}
      </div>
    </div>
  );
};

// ── Pricing card ──
interface PricingCardProps {
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  cta: string;
  featured?: boolean;
  onSelect: () => void;
}
const PricingCard: React.FC<PricingCardProps> = ({ name, price, period, description, features, cta, featured, onSelect }) => (
  <div className={`relative rounded-2xl p-8 border transition-all duration-300 hover:-translate-y-1 ${
    featured
      ? 'bg-accent/5 border-accent/30 glow-accent'
      : 'bg-panel border-border'
  }`}>
    {featured && (
      <div className="absolute -top-3 left-1/2 -translate-x-1/2">
        <span className="bg-accent text-white text-xs font-syne font-semibold px-4 py-1 rounded-full">
          Most Popular
        </span>
      </div>
    )}
    <div className="mb-6">
      <h3 className="font-syne font-semibold text-white text-lg">{name}</h3>
      <p className="text-muted text-sm mt-1 font-body">{description}</p>
    </div>
    <div className="mb-8">
      <span className="text-4xl font-display font-bold text-white">{price}</span>
      <span className="text-muted text-sm ml-1 font-body">{period}</span>
    </div>
    <ul className="space-y-3 mb-8">
      {features.map((f, i) => (
        <li key={i} className="flex items-start gap-2.5 text-sm text-soft font-body">
          <Check className={`w-4 h-4 mt-0.5 shrink-0 ${featured ? 'text-teal' : 'text-accent'}`} />
          {f}
        </li>
      ))}
    </ul>
    <button
      onClick={onSelect}
      className={`w-full py-3 rounded-xl font-syne font-semibold text-sm transition-all duration-200 ${
        featured
          ? 'bg-accent hover:bg-accent-glow text-white'
          : 'bg-border hover:bg-border text-soft hover:text-white border border-border hover:border-accent/40'
      }`}
    >
      {cta}
    </button>
  </div>
);

// ── Main landing page ──
const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-ink noise">
      <Navbar />

      {/* ── HERO ── */}
      <section className="relative min-h-screen flex items-center justify-center pt-20 overflow-hidden grid-bg">
        {/* Orbs */}
        <div className="orb orb-accent w-[600px] h-[600px] -top-48 -right-32 opacity-50" />
        <div className="orb orb-teal w-[400px] h-[400px] bottom-0 -left-20 opacity-40" />

        <div className="relative z-10 max-w-7xl mx-auto px-6 py-20">
          <div className="flex flex-col lg:flex-row items-center gap-16">
            {/* Left: Copy */}
            <div className="flex-1 text-center lg:text-left">
              <div className="inline-flex items-center gap-2 glass-light rounded-full px-4 py-1.5 mb-8 animate-fade-in">
                <Sparkles className="w-3.5 h-3.5 text-teal" />
                <span className="text-xs font-syne text-teal font-medium">AI-powered scheduling · No app downloads</span>
              </div>

              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-display font-bold leading-[1.05] mb-6 animate-slide-up">
                <span className="text-white">Schedule meetings</span>
                <br />
                <span className="text-gradient">via email.</span>
                <br />
                <span className="text-white">Automatically.</span>
              </h1>

              <p className="text-lg text-muted font-body leading-relaxed mb-10 max-w-xl mx-auto lg:mx-0 animate-slide-up stagger-2">
                CalSync.ai monitors your inbox, reads availability, coordinates across all participants,
                and books your Google Calendar — all through plain email. No new software. No friction.
              </p>

              <div className="flex flex-col sm:flex-row items-center gap-4 justify-center lg:justify-start animate-slide-up stagger-3">
                <button
                  onClick={() => navigate('/signup')}
                  className="btn-primary px-8 py-4 text-base flex items-center gap-2 glow-accent w-full sm:w-auto justify-center"
                >
                  Start for free <ArrowRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => navigate('/signin')}
                  className="px-8 py-4 text-base text-soft hover:text-white transition-colors font-syne font-medium w-full sm:w-auto"
                >
                  Sign in →
                </button>
              </div>

              <p className="text-xs text-muted mt-5 font-body animate-slide-up stagger-4">
                No credit card required · Free plan available · 2-minute setup
              </p>

              {/* Social proof */}
              <div className="flex items-center gap-3 mt-10 justify-center lg:justify-start animate-fade-in stagger-5">
                <div className="flex -space-x-2">
                  {['AJ', 'SK', 'MR', 'PD'].map((initials, i) => (
                    <div key={i} className="w-8 h-8 rounded-full bg-accent border-2 border-ink flex items-center justify-center text-xs text-white font-semibold font-syne">
                      {initials}
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-1">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="w-3.5 h-3.5 fill-amber text-amber" />
                  ))}
                </div>
                <span className="text-xs text-muted font-body">Loved by 500+ professionals</span>
              </div>
            </div>

            {/* Right: Email demo */}
            <div className="flex-1 flex justify-center lg:justify-end animate-float">
              <div className="relative">
                <div className="absolute -inset-4 bg-accent/10 rounded-3xl blur-xl" />
                <EmailDemo />
                {/* Floating badge */}
                <div className="absolute -bottom-4 -left-6 glass rounded-xl px-4 py-2.5 flex items-center gap-2.5">
                  <div className="w-6 h-6 rounded-full bg-teal/20 flex items-center justify-center">
                    <Check className="w-3 h-3 text-teal" />
                  </div>
                  <div>
                    <p className="text-xs font-syne font-semibold text-white">Meeting booked!</p>
                    <p className="text-[10px] text-muted font-body">Wed 2 PM · Google Calendar</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── TICKER ── */}
      <Ticker />

      {/* ── STATS ── */}
      <section className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <StatsSection />
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section id="how-it-works" className="py-24 px-6 relative overflow-hidden">
        <div className="orb orb-teal w-96 h-96 top-0 right-0 opacity-20" />
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="text-center mb-16">
            <span className="text-xs font-syne font-semibold text-accent-glow uppercase tracking-widest">How it works</span>
            <h2 className="text-4xl font-display font-bold text-white mt-3">
              From email to calendar in<br />
              <span className="text-gradient-accent">under 60 seconds</span>
            </h2>
          </div>

          <div className="relative">
            {/* Connector line */}
            <div className="hidden lg:block absolute top-[42px] left-[16.66%] right-[16.66%] h-px bg-gradient-to-r from-transparent via-accent/30 to-transparent" />

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
              {[
                { step: '01', icon: <Mail className="w-5 h-5" />, title: 'Email arrives', desc: 'Someone emails your CalSync address requesting a meeting or sharing availability.' },
                { step: '02', icon: <Cpu className="w-5 h-5" />, title: 'AI parses intent', desc: 'Our LLM + spaCy NLP extracts dates, times, timezones and scheduling intent instantly.' },
                { step: '03', icon: <Users className="w-5 h-5" />, title: 'Coordinates all parties', desc: 'Queries each participant, collects replies, and computes the optimal overlapping slot.' },
                { step: '04', icon: <Calendar className="w-5 h-5" />, title: 'Books & confirms', desc: 'Creates the Google Calendar event and sends invites with AI disclaimer to everyone.' },
              ].map((item, i) => (
                <div key={i} className="flex flex-col items-center text-center lg:items-start lg:text-left relative">
                  <div className="w-[84px] h-[84px] rounded-2xl bg-panel border border-border flex flex-col items-center justify-center gap-1 mb-5 relative z-10">
                    <span className="text-[10px] font-syne font-semibold text-muted">{item.step}</span>
                    <span className="text-accent-glow">{item.icon}</span>
                  </div>
                  <h3 className="font-syne font-semibold text-white text-base mb-2">{item.title}</h3>
                  <p className="text-sm text-muted font-body leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section id="features" className="py-24 px-6 bg-surface/30">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <span className="text-xs font-syne font-semibold text-accent-glow uppercase tracking-widest">Features</span>
            <h2 className="text-4xl font-display font-bold text-white mt-3">
              Everything you need.<br />
              <span className="text-gradient-accent">Nothing you don't.</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <FeatureCard
              accent
              icon={<Zap className="w-5 h-5" />}
              title="Autonomous Email Agent"
              description="Reads every email, understands scheduling context, coordinates participants — all without any human intervention."
              tag="Core"
            />
            <FeatureCard
              icon={<MessageSquare className="w-5 h-5" />}
              title="Natural Language Parsing"
              description="Understands free-form availability like 'anytime Monday except lunch' using spaCy NLP and deterministic time parsing."
            />
            <FeatureCard
              icon={<Globe className="w-5 h-5" />}
              title="Multi-Timezone Intelligence"
              description="Automatically converts everyone's availability to UTC, finds overlaps, and books using each person's local time."
            />
            <FeatureCard
              icon={<RefreshCw className="w-5 h-5" />}
              title="Conflict Recovery"
              description="Pre-computes top 3 backup slots. If the primary slot is taken at booking time, it auto-books the next best option."
            />
            <FeatureCard
              icon={<Shield className="w-5 h-5" />}
              title="Duplicate Protection"
              description="SHA-256 fingerprinting on every email ensures no double-bookings even with network retries or forwarded chains."
              tag="Security"
            />
            <FeatureCard
              icon={<BarChart2 className="w-5 h-5" />}
              title="Priority-Aware Scheduling"
              description="Weight key stakeholders higher in the overlap algorithm so critical participants' availability is always prioritized."
            />
            <FeatureCard
              icon={<Clock className="w-5 h-5" />}
              title="Status Intelligence"
              description="Ask for a meeting update at any time. The AI reads the full thread and replies with a human-readable summary instantly."
            />
            <FeatureCard
              icon={<Calendar className="w-5 h-5" />}
              title="Google Calendar Integration"
              description="Creates events, sends invites with video links, and syncs cancellations — all via secure OAuth 2.0."
            />
            <FeatureCard
              icon={<Users className="w-5 h-5" />}
              title="Unlimited Participants"
              description="Coordinate meetings with 2 to 50+ participants. The O(NM) matrix overlap algorithm scales effortlessly."
              tag="Unlimited"
            />
          </div>
        </div>
      </section>

      {/* ── COMPARISON ── */}
      <section className="py-24 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-display font-bold text-white">
              Why <span className="text-gradient-accent">CalSync.ai</span>?
            </h2>
            <p className="text-muted mt-3 font-body">The only tool that works entirely through email</p>
          </div>

          <div className="glass rounded-2xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-6 py-4 text-sm font-syne font-semibold text-soft">Capability</th>
                  <th className="px-6 py-4 text-sm font-syne font-semibold text-accent-glow">CalSync.ai</th>
                  <th className="px-6 py-4 text-sm font-syne font-semibold text-muted">Calendly</th>
                  <th className="px-6 py-4 text-sm font-syne font-semibold text-muted">Reclaim.ai</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {[
                  ['Fully autonomous scheduling', true, false, true],
                  ['Works through plain email', true, false, false],
                  ['Natural language replies', true, false, false],
                  ['Unlimited multi-party coordination', true, true, false],
                  ['No app required', true, false, false],
                  ['Conflict auto-recovery', true, false, false],
                ].map(([cap, cs, ca, re], i) => (
                  <tr key={i} className="hover:bg-white/1 transition-colors">
                    <td className="px-6 py-3.5 text-sm text-soft font-body">{cap as string}</td>
                    {[cs, ca, re].map((val, j) => (
                      <td key={j} className="px-6 py-3.5 text-center">
                        {val
                          ? <Check className={`w-4 h-4 mx-auto ${j === 0 ? 'text-teal' : 'text-muted'}`} />
                          : <span className="text-muted text-lg">—</span>
                        }
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="pricing" className="py-24 px-6 bg-surface/30">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <span className="text-xs font-syne font-semibold text-accent-glow uppercase tracking-widest">Pricing</span>
            <h2 className="text-4xl font-display font-bold text-white mt-3">Simple, transparent pricing</h2>
            <p className="text-muted mt-3 font-body">Start free. Upgrade when you need more.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <PricingCard
              name="Starter"
              price="Free"
              period="forever"
              description="For individuals getting started"
              features={[
                '10 meetings/month',
                '1 connected email',
                'Basic NLP parsing',
                'Google Calendar sync',
                'AI email disclaimer',
              ]}
              cta="Get started free"
              onSelect={() => navigate('/signup')}
            />
            <PricingCard
              name="Pro"
              price="₹999"
              period="/month"
              description="For professionals and teams"
              features={[
                'Unlimited meetings',
                '3 connected emails',
                'Advanced NLP + timezone AI',
                'Priority-aware scheduling',
                'Conflict auto-recovery',
                'Live dashboard & analytics',
              ]}
              cta="Start Pro trial"
              featured
              onSelect={() => navigate('/signup')}
            />
            <PricingCard
              name="Enterprise"
              price="Custom"
              period="pricing"
              description="For large organizations"
              features={[
                'Unlimited everything',
                'Custom CalSync domains',
                'SSO & admin controls',
                'SLA guarantee',
                'Dedicated support',
              ]}
              cta="Contact sales"
              onSelect={() => {}}
            />
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-32 px-6 relative overflow-hidden">
        <div className="orb orb-accent w-[500px] h-[500px] -top-20 left-1/2 -translate-x-1/2 opacity-30" />
        <div className="max-w-3xl mx-auto text-center relative z-10">
          <h2 className="text-5xl font-display font-bold text-white leading-tight mb-6">
            Stop scheduling.<br />
            <span className="text-gradient">Start meeting.</span>
          </h2>
          <p className="text-lg text-muted font-body mb-10">
            Join professionals who've reclaimed hours every week by letting CalSync.ai handle every scheduling email automatically.
          </p>
          <button
            onClick={() => navigate('/signup')}
            className="btn-primary px-10 py-4 text-lg glow-accent inline-flex items-center gap-3"
          >
            Get started free <ChevronRight className="w-5 h-5" />
          </button>
          <p className="text-xs text-muted mt-4 font-body">No credit card · 2-minute setup · Cancel anytime</p>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="border-t border-border py-10 px-6">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-accent flex items-center justify-center">
              <Calendar className="w-3 h-3 text-white" />
            </div>
            <span className="font-display font-bold text-white text-sm">CalSync<span className="text-accent-glow">.ai</span></span>
          </div>
          <p className="text-xs text-muted font-body">
            Built by Team ByteMinds · PICT, Pune · Experimental AI project
          </p>
          <div className="flex items-center gap-6">
            {['Privacy', 'Terms', 'Contact'].map(l => (
              <a key={l} href="#" className="text-xs text-muted hover:text-soft transition-colors font-body">{l}</a>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
