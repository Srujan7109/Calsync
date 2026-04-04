import { useEffect, Suspense, lazy, type ReactNode } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { supabase } from "./lib/supabase";
import { useAuthStore } from "./stores/authstore.ts";
import Sidebar from "./components/layout/Sidebar";
import TopBar from "./components/layout/TopBar";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const SessionDetail = lazy(() => import("./pages/SessionDetail"));
const Calendar = lazy(() => import("./pages/Calendar"));
const EmailFeed = lazy(() => import("./pages/EmailFeed"));
const Preferences = lazy(() => import("./pages/Preferences"));
const Logs = lazy(() => import("./pages/Logs"));
const Settings = lazy(() => import("./pages/Settings"));
const Login = lazy(() => import("./pages/Login"));
const NotFound = lazy(() => import("./pages/NotFound"));

function FullPageMessage({ message }: { message: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center">
      {message}
    </div>
  );
}

function AuthGuard({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuthStore();

  if (isLoading) return <FullPageMessage message="Loading..." />;
  if (!user) return <Navigate to="/login" replace />;

  return <>{children}</>;
}

function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg)]">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <Suspense fallback={<div className="p-6">Loading view...</div>}>
            {children}
          </Suspense>
        </main>
      </div>
    </div>
  );
}

function App() {
  const { setUser, setLoading } = useAuthStore();

  useEffect(() => {
    let active = true;

    supabase.auth
      .getSession()
      .then(({ data: { session } }) => {
        if (!active) return;
        setUser(session?.user ?? null);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [setUser, setLoading]);

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            <Suspense fallback={<div className="p-6">Loading...</div>}>
              <Login />
            </Suspense>
          }
        />

        <Route
          path="/"
          element={
            <AuthGuard>
              <AppLayout>
                <Dashboard />
              </AppLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/sessions/:session_id"
          element={
            <AuthGuard>
              <AppLayout>
                <SessionDetail />
              </AppLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/calendar"
          element={
            <AuthGuard>
              <AppLayout>
                <Calendar />
              </AppLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/emails"
          element={
            <AuthGuard>
              <AppLayout>
                <EmailFeed />
              </AppLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/preferences"
          element={
            <AuthGuard>
              <AppLayout>
                <Preferences />
              </AppLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/logs"
          element={
            <AuthGuard>
              <AppLayout>
                <Logs />
              </AppLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/settings"
          element={
            <AuthGuard>
              <AppLayout>
                <Settings />
              </AppLayout>
            </AuthGuard>
          }
        />
        <Route
          path="*"
          element={
            <AuthGuard>
              <AppLayout>
                <NotFound />
              </AppLayout>
            </AuthGuard>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
