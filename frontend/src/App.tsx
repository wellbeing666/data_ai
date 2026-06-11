import { useEffect, useState } from "react";

import { fetchCurrentUser, getStoredAuthToken, logout, setStoredAuthToken } from "./api";
import { AppSidebar } from "./components/AppSidebar";
import { AuthFormCard, AuthFrame } from "./components/auth/AuthLayout";
import { isWorkbenchPage, pageTitles, roleLabel, statusLabel, type AppPageKey } from "./navigation";
import { LoginPage } from "./pages/auth/LoginPage";
import { RegisterPage } from "./pages/auth/RegisterPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { AdminPage } from "./pages/system/AdminPage";
import { AccountPage } from "./pages/system/AccountPage";
import type { AuthUser } from "./types";

type AuthView = "login" | "register";

export default function App() {
  const [authView, setAuthView] = useState<AuthView>("login");
  const [activePage, setActivePage] = useState<AppPageKey>("overview");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const token = getStoredAuthToken();
    if (!token) {
      setBooting(false);
      return;
    }
    fetchCurrentUser()
      .then((response) => {
        setUser(response.user);
        setActivePage("overview");
      })
      .catch(() => {
        setStoredAuthToken(null);
        setUser(null);
      })
      .finally(() => setBooting(false));
  }, []);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      setStoredAuthToken(null);
      setUser(null);
      setAuthView("login");
      setActivePage("overview");
      setMessage("已退出登录。");
    }
  }

  if (booting) {
    return (
      <AuthFrame>
        <AuthFormCard eyebrow="AI 数据分析工作台" title="正在进入工作台" description="正在校验登录状态，请稍候。" />
      </AuthFrame>
    );
  }

  if (!user) {
    return authView === "register" ? (
      <RegisterPage
        globalMessage={message}
        onBack={() => setAuthView("login")}
        onMessage={setMessage}
      />
    ) : (
      <LoginPage
        globalMessage={message}
        onRegister={() => setAuthView("register")}
        onLoggedIn={(token, nextUser) => {
          setStoredAuthToken(token);
          setUser(nextUser);
          setMessage("");
          setActivePage("overview");
        }}
      />
    );
  }

  return (
    <main className="app-frame">
      <AppSidebar user={user} activePage={activePage} onPageChange={setActivePage} onLogout={handleLogout} />
      <section className="app-main">
        <header className="app-topbar">
          <div>
            <p className="eyebrow">AI 数据分析工作台</p>
            <h1>{pageTitles[activePage]}</h1>
          </div>
          <div className="topbar-actions">
            <span className="badge badge-secondary">{roleLabel(user.role)}</span>
            <span className="badge badge-outline">{statusLabel(user.status)}</span>
          </div>
        </header>
        {isWorkbenchPage(activePage) ? (
          <WorkbenchPage currentUser={user} activePage={activePage} onPageChange={setActivePage} />
        ) : null}
        {activePage === "account" ? <AccountPage user={user} onUserChange={setUser} onLogout={handleLogout} /> : null}
        {activePage === "admin" && user.role === "admin" ? <AdminPage currentUser={user} /> : null}
      </section>
    </main>
  );
}
