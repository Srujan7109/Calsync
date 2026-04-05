import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Calendar,
  Mail,
  Copy,
  Check,
  Clock,
  Users,
  LogOut,
  Bell,
  ChevronRight,
  Inbox,
  Zap,
  Plus,
  RefreshCw,
  ExternalLink,
  AlertCircle,
  CheckCircle2,
  Loader2,
  MessageSquare,
  TrendingUp,
  Settings,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

// ── Types ──
type MeetingStatus = "awaiting" | "computing" | "booked" | "failed";
type DashboardView = "dashboard" | "settings";

interface Meeting {
  id: string;
  subject: string;
  initiator: string;
  participants: string[];
  status: MeetingStatus;
  slot?: string;
  createdAt: string;
  threadCount: number;
}

// ── Seed data ──
const SEED_MEETINGS: Meeting[] = [
  {
    id: "1",
    subject: "Q3 Strategy Sync",
    initiator: "sarah@acmecorp.com",
    participants: ["sarah@acmecorp.com", "mike@startup.io", "priya@design.co"],
    status: "booked",
    slot: "Wed, Apr 9 · 2:00–3:00 PM IST",
    createdAt: "2 hours ago",
    threadCount: 6,
  },
  {
    id: "2",
    subject: "Product Demo — Investors",
    initiator: "vc@fundfirm.com",
    participants: ["vc@fundfirm.com", "you@yourco.com"],
    status: "awaiting",
    createdAt: "45 min ago",
    threadCount: 2,
  },
  {
    id: "3",
    subject: "Sprint Planning",
    initiator: "dev@team.io",
    participants: ["dev@team.io", "pm@team.io", "design@team.io", "qa@team.io"],
    status: "computing",
    createdAt: "12 min ago",
    threadCount: 8,
  },
  {
    id: "4",
    subject: "Client Onboarding Call",
    initiator: "client@enterprise.com",
    participants: ["client@enterprise.com", "success@yourco.com"],
    status: "booked",
    slot: "Mon, Apr 7 · 10:30 AM IST",
    createdAt: "1 day ago",
    threadCount: 4,
  },
  {
    id: "5",
    subject: "1:1 with Mentor",
    initiator: "mentor@iitb.ac.in",
    participants: ["mentor@iitb.ac.in"],
    status: "failed",
    createdAt: "2 days ago",
    threadCount: 3,
  },
];

// ── Status badge ──
const StatusBadge: React.FC<{ status: MeetingStatus }> = ({ status }) => {
  const config = {
    awaiting: {
      label: "Awaiting replies",
      color: "text-amber bg-amber/10 border-amber/20",
      icon: <Clock className="w-3 h-3" />,
    },
    computing: {
      label: "Computing overlap",
      color: "text-accent-glow bg-accent/10 border-accent/20",
      icon: <Loader2 className="w-3 h-3 animate-spin" />,
    },
    booked: {
      label: "Booked",
      color: "text-teal bg-teal/10 border-teal/20",
      icon: <CheckCircle2 className="w-3 h-3" />,
    },
    failed: {
      label: "Needs attention",
      color: "text-red-400 bg-red-500/10 border-red-500/20",
      icon: <AlertCircle className="w-3 h-3" />,
    },
  }[status];

  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[11px] font-syne font-semibold px-2 py-1 rounded-full border ${config.color}`}
    >
      {config.icon} {config.label}
    </span>
  );
};

// ── Funnel step ──
const FunnelStep: React.FC<{
  label: string;
  count: number;
  active?: boolean;
}> = ({ label, count, active }) => (
  <div
    className={`flex-1 rounded-xl p-4 border text-center transition-all ${active ? "bg-accent/5 border-accent/25" : "bg-panel border-border"}`}
  >
    <div
      className={`text-2xl font-display font-bold ${active ? "text-accent-glow" : "text-white"}`}
    >
      {count}
    </div>
    <div className="text-xs text-muted font-body mt-1">{label}</div>
  </div>
);

// ── Copied toast ──
const CopiedToast: React.FC<{ show: boolean }> = ({ show }) => (
  <div
    className={`fixed bottom-6 right-6 glass rounded-xl px-4 py-3 flex items-center gap-2 text-sm text-teal font-body z-50 transition-all duration-300 ${show ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4 pointer-events-none"}`}
  >
    <Check className="w-4 h-4" /> Copied to clipboard!
  </div>
);

// ── Main dashboard ──
const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const [meetings, setMeetings] = useState<Meeting[]>(SEED_MEETINGS);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<"all" | MeetingStatus>("all");
  const [activeView, setActiveView] = useState<DashboardView>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [defaultDuration, setDefaultDuration] = useState("30");
  const [bufferTime, setBufferTime] = useState("10");
  const [workdayStart, setWorkdayStart] = useState("09:00");
  const [workdayEnd, setWorkdayEnd] = useState("18:00");

  if (!user) {
    navigate("/signin");
    return null;
  }

  const calSyncAddress = user.calSyncAddress || "you@calsync.ai";

  const copyAddress = () => {
    navigator.clipboard.writeText("calsync1.ai@gmail.com");
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const filteredMeetings =
    activeTab === "all"
      ? meetings
      : meetings.filter((m) => m.status === activeTab);

  const stats = {
    total: meetings.length,
    booked: meetings.filter((m) => m.status === "booked").length,
    computing: meetings.filter((m) => m.status === "computing").length,
    awaiting: meetings.filter((m) => m.status === "awaiting").length,
  };

  const retryMeeting = (id: string) => {
    setMeetings((prev) =>
      prev.map((m) => (m.id === id ? { ...m, status: "awaiting" } : m)),
    );
  };

  const handleSignOut = () => {
    signOut();
    navigate("/");
  };

  const handleSaveSettings = () => {
    setSettingsSaved(true);
    setTimeout(() => setSettingsSaved(false), 2500);
  };

  return (
    <div className="min-h-screen bg-ink flex">
      {/* ── Sidebar ── */}
      <aside
        className={`${sidebarOpen ? "w-64" : "w-16"} bg-surface border-r border-border flex flex-col transition-all duration-300 shrink-0 fixed top-0 left-0 h-full z-40`}
      >
        {/* Logo */}
        <div className="p-4 border-b border-border">
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-2.5 overflow-hidden"
          >
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center shrink-0">
              <Calendar className="w-4 h-4 text-white" />
            </div>
            {sidebarOpen && (
              <span className="font-display font-bold text-lg text-white whitespace-nowrap">
                CalSync<span className="text-accent-glow">.ai</span>
              </span>
            )}
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-1">
          {[
            {
              icon: <Inbox className="w-4 h-4" />,
              label: "Dashboard",
              view: "dashboard" as DashboardView,
            },
            {
              icon: <Settings className="w-4 h-4" />,
              label: "Settings",
              view: "settings" as DashboardView,
            },
          ].map((item) => (
            <button
              key={item.label}
              onClick={() => setActiveView(item.view)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 group ${
                activeView === item.view
                  ? "bg-accent/10 text-accent-glow"
                  : "text-muted hover:text-soft hover:bg-border/50"
              }`}
            >
              {item.icon}
              {sidebarOpen && (
                <span className="text-sm font-body whitespace-nowrap">
                  {item.label}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* User */}
        <div className="p-3 border-t border-border">
          <div className="flex items-center gap-2.5 mb-2">
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-xs font-semibold font-syne shrink-0">
              {user.avatar}
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-xs font-syne font-semibold text-white truncate">
                  {user.name}
                </p>
                <p className="text-[10px] text-muted font-body truncate">
                  {user.plan === "free" ? "Free plan" : "Pro"}
                </p>
              </div>
            )}
          </div>
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-muted hover:text-red-400 hover:bg-red-500/5 transition-all text-xs font-body"
          >
            <LogOut className="w-3.5 h-3.5" />
            {sidebarOpen && "Sign out"}
          </button>
        </div>

        {/* Collapse toggle */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="absolute -right-3 top-20 w-6 h-6 bg-surface border border-border rounded-full flex items-center justify-center text-muted hover:text-soft"
        >
          <ChevronRight
            className={`w-3 h-3 transition-transform ${sidebarOpen ? "rotate-180" : ""}`}
          />
        </button>
      </aside>

      {/* ── Main content ── */}
      <main
        className={`flex-1 ${sidebarOpen ? "ml-64" : "ml-16"} transition-all duration-300`}
      >
        {/* Top bar */}
        <header className="sticky top-0 z-30 glass border-b border-border px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-syne font-bold text-white">
              {activeView === "dashboard" ? "Scheduling Dashboard" : "Settings"}
            </h1>
            <p className="text-xs text-muted font-body mt-0.5">
              {activeView === "dashboard"
                ? "All your automated meetings in one place"
                : "Control your scheduling preferences and notifications"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button className="relative p-2 text-muted hover:text-soft transition-colors">
              <Bell className="w-4 h-4" />
              <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-accent rounded-full" />
            </button>
            {activeView === "dashboard" ? (
              <button
                onClick={() => setShowAddModal(true)}
                className="btn-primary text-xs px-4 py-2 flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" /> New meeting
              </button>
            ) : (
              <button
                onClick={handleSaveSettings}
                className="btn-primary text-xs px-4 py-2"
              >
                Save settings
              </button>
            )}
          </div>
        </header>

        <div className="p-6 space-y-6">
          {activeView === "dashboard" ? (
            <>
              {/* ── CalSync Address Banner ── */}
              <div className="relative bg-gradient-to-r from-accent/10 via-accent/5 to-transparent border border-accent/20 rounded-2xl p-5 overflow-hidden">
                <div className="absolute right-0 top-0 bottom-0 w-32 bg-gradient-to-l from-teal/5 to-transparent pointer-events-none" />
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center shrink-0">
                    <Mail className="w-5 h-5 text-accent-glow" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1">
                      CalSync address
                    </p>
                    <p className="text-lg font-syne font-bold text-white truncate">
                      calsync1.ai@gmail.com
                    </p>
                    <p className="text-xs text-muted font-body mt-0.5">
                      CC or tag this address in any email thread to trigger
                      automatic scheduling
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={copyAddress}
                      className="flex items-center gap-2 glass-light rounded-xl px-4 py-2.5 text-sm font-syne font-medium text-soft hover:text-white transition-colors"
                    >
                      {copied ? (
                        <Check className="w-4 h-4 text-teal" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )}
                      {copied ? "Copied!" : "Copy"}
                    </button>
                    <button className="p-2.5 glass-light rounded-xl text-muted hover:text-soft transition-colors">
                      <ExternalLink className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>

              {/* ── Stats cards ── */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  {
                    label: "Total threads",
                    value: stats.total,
                    icon: <Inbox className="w-4 h-4" />,
                    color: "text-soft",
                  },
                  {
                    label: "Meetings booked",
                    value: stats.booked,
                    icon: <CheckCircle2 className="w-4 h-4" />,
                    color: "text-teal",
                  },
                  {
                    label: "Hours saved",
                    value: `${(stats.booked * 0.8).toFixed(1)}h`,
                    icon: <TrendingUp className="w-4 h-4" />,
                    color: "text-accent-glow",
                  },
                  {
                    label: "In progress",
                    value: stats.computing + stats.awaiting,
                    icon: <Zap className="w-4 h-4" />,
                    color: "text-amber",
                  },
                ].map((stat, i) => (
                  <div
                    key={i}
                    className="bg-panel border border-border rounded-2xl p-5"
                  >
                    <div className={`${stat.color} mb-3`}>{stat.icon}</div>
                    <div className="text-2xl font-display font-bold text-white">
                      {stat.value}
                    </div>
                    <div className="text-xs text-muted font-body mt-1">
                      {stat.label}
                    </div>
                  </div>
                ))}
              </div>

              {/* ── Funnel ── */}
              <div>
                <h2 className="text-sm font-syne font-semibold text-soft mb-3">
                  Coordination funnel
                </h2>
                <div className="flex items-center gap-2">
                  <FunnelStep label="Awaiting replies" count={stats.awaiting} />
                  <ChevronRight className="text-muted shrink-0" />
                  <FunnelStep
                    label="Computing overlap"
                    count={stats.computing}
                    active
                  />
                  <ChevronRight className="text-muted shrink-0" />
                  <FunnelStep label="Booked" count={stats.booked} />
                </div>
              </div>

              {/* ── How to use ── */}
              <div className="bg-panel border border-border rounded-2xl p-5">
                <h2 className="text-sm font-syne font-semibold text-white mb-4 flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-accent-glow" /> How to
                  trigger CalSync.ai
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {[
                    {
                      step: "1",
                      title: "CC your address",
                      desc: `Add calsync1.ai@gmail.com to the CC field of any scheduling email`,
                      example: `To: colleague@work.com\nCC: calsync1.ai@gmail.com`,
                    },
                    {
                      step: "2",
                      title: "Share availability",
                      desc: "Write your availability in plain text — the AI understands natural language",
                      example: `"I'm free Mon 2-4pm or\nWed anytime after 10am"`,
                    },
                    {
                      step: "3",
                      title: "Relax",
                      desc: "CalSync coordinates everyone, finds the overlap, books Calendar, and sends invites",
                      example: `📅 Meeting confirmed:\nWed 2-3 PM · Google Calendar invite sent`,
                    },
                  ].map((step) => (
                    <div key={step.step} className="bg-surface rounded-xl p-4">
                      <div className="w-6 h-6 rounded-full bg-accent/20 flex items-center justify-center text-xs font-syne font-bold text-accent-glow mb-3">
                        {step.step}
                      </div>
                      <h3 className="text-sm font-syne font-semibold text-white mb-1">
                        {step.title}
                      </h3>
                      <p className="text-xs text-muted font-body leading-relaxed mb-3">
                        {step.desc}
                      </p>
                      <div className="bg-ink rounded-lg px-3 py-2 text-[11px] text-teal font-mono whitespace-pre">
                        {step.example}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* ── Meeting list ── */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-syne font-semibold text-white">
                    Email threads
                  </h2>
                  <div className="flex items-center gap-1 bg-panel border border-border rounded-xl p-1">
                    {(
                      [
                        "all",
                        "awaiting",
                        "computing",
                        "booked",
                        "failed",
                      ] as const
                    ).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-syne font-medium transition-all ${
                          activeTab === tab
                            ? "bg-accent text-white"
                            : "text-muted hover:text-soft"
                        }`}
                      >
                        {tab === "all"
                          ? "All"
                          : tab.charAt(0).toUpperCase() + tab.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  {filteredMeetings.length === 0 && (
                    <div className="bg-panel border border-border rounded-2xl p-10 text-center">
                      <Inbox className="w-8 h-8 text-muted mx-auto mb-3" />
                      <p className="text-soft text-sm font-body">
                        No threads in this category
                      </p>
                    </div>
                  )}
                  {filteredMeetings.map((meeting) => (
                    <div
                      key={meeting.id}
                      className="bg-panel border border-border rounded-2xl p-4 hover:border-border hover:bg-surface/50 transition-all duration-200 group"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3 flex-1 min-w-0">
                          {/* Status indicator dot */}
                          <div
                            className={`w-2 h-2 rounded-full mt-2 shrink-0 ${
                              meeting.status === "booked"
                                ? "bg-teal"
                                : meeting.status === "computing"
                                  ? "bg-accent animate-pulse"
                                  : meeting.status === "awaiting"
                                    ? "bg-amber"
                                    : "bg-red-400"
                            }`}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start gap-3 flex-wrap">
                              <h3 className="text-sm font-syne font-semibold text-white">
                                {meeting.subject}
                              </h3>
                              <StatusBadge status={meeting.status} />
                            </div>
                            <p className="text-xs text-muted font-body mt-1 truncate">
                              From: {meeting.initiator}
                            </p>
                            {meeting.slot && (
                              <p className="text-xs text-teal font-body mt-1 flex items-center gap-1">
                                <Calendar className="w-3 h-3" /> {meeting.slot}
                              </p>
                            )}
                            <div className="flex items-center gap-4 mt-2">
                              <span className="text-[11px] text-muted font-body flex items-center gap-1">
                                <Users className="w-3 h-3" />{" "}
                                {meeting.participants.length} participant
                                {meeting.participants.length !== 1 ? "s" : ""}
                              </span>
                              <span className="text-[11px] text-muted font-body flex items-center gap-1">
                                <MessageSquare className="w-3 h-3" />{" "}
                                {meeting.threadCount} emails
                              </span>
                              <span className="text-[11px] text-muted font-body">
                                {meeting.createdAt}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                          {meeting.status === "failed" && (
                            <button
                              onClick={() => retryMeeting(meeting.id)}
                              className="flex items-center gap-1.5 text-xs text-amber hover:text-white bg-amber/10 hover:bg-amber/20 px-3 py-1.5 rounded-lg transition-all font-body"
                            >
                              <RefreshCw className="w-3 h-3" /> Retry
                            </button>
                          )}
                          <button className="p-1.5 text-muted hover:text-soft transition-colors">
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      </div>

                      {/* Participant avatars */}
                      {meeting.participants.length > 0 && (
                        <div className="flex items-center gap-1 mt-3 pl-5">
                          {meeting.participants.slice(0, 4).map((p, i) => (
                            <div
                              key={i}
                              title={p}
                              className="w-6 h-6 rounded-full bg-accent/20 border border-ink flex items-center justify-center text-[9px] font-semibold text-accent-glow -ml-1 first:ml-0"
                            >
                              {p[0].toUpperCase()}
                            </div>
                          ))}
                          {meeting.participants.length > 4 && (
                            <div className="w-6 h-6 rounded-full bg-border border border-ink flex items-center justify-center text-[9px] text-muted -ml-1">
                              +{meeting.participants.length - 4}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              {settingsSaved && (
                <div className="bg-teal/10 border border-teal/30 rounded-xl px-4 py-3 text-sm text-teal font-body">
                  Settings saved successfully.
                </div>
              )}

              <div className="bg-panel border border-border rounded-2xl p-5 space-y-5">
                  <div>
                    <h2 className="text-sm font-syne font-semibold text-white mb-1">
                      Profile
                    </h2>
                    <p className="text-xs text-muted font-body">
                      Basic account information used across scheduling emails.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                        Full name
                      </label>
                      <input
                        type="text"
                        value={user.name}
                        readOnly
                        className="input-field opacity-80 cursor-not-allowed"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                        Email
                      </label>
                      <input
                        type="email"
                        value={user.email}
                        readOnly
                        className="input-field opacity-80 cursor-not-allowed"
                      />
                    </div>
                  </div>

                  <div className="pt-2">
                    <h2 className="text-sm font-syne font-semibold text-white mb-3">
                      Scheduling defaults
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                          Timezone
                        </label>
                        <select
                          value={timezone}
                          onChange={(e) => setTimezone(e.target.value)}
                          className="input-field"
                        >
                          <option value="Asia/Kolkata">
                            Asia/Kolkata (IST)
                          </option>
                          <option value="Europe/London">
                            Europe/London (GMT/BST)
                          </option>
                          <option value="America/New_York">
                            America/New_York (ET)
                          </option>
                          <option value="America/Los_Angeles">
                            America/Los_Angeles (PT)
                          </option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                          Default meeting duration
                        </label>
                        <select
                          value={defaultDuration}
                          onChange={(e) => setDefaultDuration(e.target.value)}
                          className="input-field"
                        >
                          <option value="15">15 minutes</option>
                          <option value="30">30 minutes</option>
                          <option value="45">45 minutes</option>
                          <option value="60">60 minutes</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                          Daily start time
                        </label>
                        <input
                          type="time"
                          value={workdayStart}
                          onChange={(e) => setWorkdayStart(e.target.value)}
                          className="input-field"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                          Daily end time
                        </label>
                        <input
                          type="time"
                          value={workdayEnd}
                          onChange={(e) => setWorkdayEnd(e.target.value)}
                          className="input-field"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-syne font-semibold text-muted uppercase tracking-wider mb-1.5">
                          Buffer between meetings
                        </label>
                        <select
                          value={bufferTime}
                          onChange={(e) => setBufferTime(e.target.value)}
                          className="input-field"
                        >
                          <option value="0">No buffer</option>
                          <option value="5">5 minutes</option>
                          <option value="10">10 minutes</option>
                          <option value="15">15 minutes</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>
            </>
          )}
        </div>
      </main>

      {/* ── Add Meeting Modal ── */}
      {showAddModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={() => setShowAddModal(false)}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div
            className="relative glass rounded-2xl p-6 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-syne font-bold text-white mb-1">
              Start a new meeting thread
            </h2>
            <p className="text-xs text-muted font-body mb-5">
              Simply CC{" "}
              <span className="text-accent-glow font-medium">
                {calSyncAddress}
              </span>{" "}
              in your next scheduling email. Or paste the thread details below.
            </p>
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Meeting subject"
                className="input-field"
              />
              <input
                type="email"
                placeholder="Participant emails (comma separated)"
                className="input-field"
              />
              <textarea
                placeholder="Availability details (optional — e.g. 'I'm free Mon-Wed after 2pm')"
                className="input-field h-20 resize-none"
              />
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => setShowAddModal(false)}
                className="flex-1 py-2.5 rounded-xl border border-border text-muted hover:text-soft text-sm font-body transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const newMeeting: Meeting = {
                    id: String(Date.now()),
                    subject: "New Meeting Request",
                    initiator: user.email,
                    participants: [user.email],
                    status: "awaiting",
                    createdAt: "just now",
                    threadCount: 1,
                  };
                  setMeetings((prev) => [newMeeting, ...prev]);
                  setShowAddModal(false);
                }}
                className="flex-1 btn-primary py-2.5 text-sm"
              >
                Create thread
              </button>
            </div>
          </div>
        </div>
      )}

      <CopiedToast show={copied} />
    </div>
  );
};

export default DashboardPage;
