// frontend/src/App.tsx
import { Component, type ErrorInfo, type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import {
  changeAdminUserRole,
  changeMyPassword,
  fetchAdminUsers,
  fetchCurrentUser,
  freezeAdminUser,
  getStoredAuthToken,
  login,
  logout,
  registerUser,
  reviewAdminUser,
  setStoredAuthToken,
  updateMyProfile
} from "./api";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import type { AuthUser } from "./types";

type AppView = "login" | "register" | "workbench" | "account" | "admin";

const GameStyles = () => (
  <style>{`
    :root {
      --game-bg: #F5FBFF;
      --game-primary: #0ea5e9;
      --game-primary-hover: #0284c7;
      --game-panel: rgba(255, 255, 255, 0.85);
      --game-border: #bae6fd;
    }

    body {
      background-color: var(--game-bg) !important;
      background-image: 
        radial-gradient(circle at 15% 50%, rgba(14, 165, 233, 0.08), transparent 25%),
        radial-gradient(circle at 85% 30%, rgba(14, 165, 233, 0.08), transparent 25%) !important;
      animation: gameBgPan 20s infinite alternate linear;
    }

    .mode-banner, .issue-list article, .source-notice, .history-empty, .warning {
      background-color: #F5FBFF !important;
      border-color: #bae6fd !important;
      color: #0369a1 !important;
    }

    @keyframes gameBgPan {
      0% { background-position: 0% 0%; }
      100% { background-position: 100% 100%; }
    }

    @keyframes floatAvatar {
      0% { transform: translateY(0px); filter: drop-shadow(0 5px 15px rgba(14,165,233,0.3)); }
      50% { transform: translateY(-12px); filter: drop-shadow(0 15px 25px rgba(14,165,233,0.5)); }
      100% { transform: translateY(0px); filter: drop-shadow(0 5px 15px rgba(14,165,233,0.3)); }
    }

    @keyframes pulseGlow {
      0% { box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.4); }
      70% { box-shadow: 0 0 10px 10px rgba(14, 165, 233, 0); }
      100% { box-shadow: 0 0 0 0 rgba(14, 165, 233, 0); }
    }

    .auth-card, .settings-card, .panel, .content-panel {
      background: var(--game-panel) !important;
      backdrop-filter: blur(12px) !important;
      border: 2px solid var(--game-border) !important;
      border-radius: 20px !important;
      box-shadow: 0 8px 32px rgba(14, 165, 233, 0.15) !important;
      transition: transform 0.3s ease, box-shadow 0.3s ease !important;
    }
    
    .auth-card:hover, .settings-card:hover {
      transform: translateY(-4px);
      box-shadow: 0 12px 40px rgba(14, 165, 233, 0.25) !important;
    }

    .primary-button {
      background: linear-gradient(135deg, var(--game-primary), var(--game-primary-hover)) !important;
      border: none !important;
      border-radius: 12px !important;
      text-transform: uppercase;
      letter-spacing: 1px;
      font-weight: 800 !important;
      transition: all 0.2s !important;
      box-shadow: 0 4px 15px rgba(14, 165, 233, 0.3) !important;
    }

    .primary-button:hover:not(:disabled) {
      transform: scale(1.03);
      animation: pulseGlow 1.5s infinite;
    }
    
    .game-avatar {
      margin: 0 auto 20px;
      animation: floatAvatar 3s ease-in-out infinite;
    }

    input, textarea, select {
      border-radius: 10px !important;
      border: 2px solid #cbd5e1 !important;
      transition: all 0.3s !important;
    }

    input:focus, textarea:focus, select:focus {
      border-color: var(--game-primary) !important;
      box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.2) !important;
    }
    
    .app-header {
      background: rgba(245, 251, 255, 0.9) !important;
      backdrop-filter: blur(10px);
      border-bottom: 2px solid var(--game-border) !important;
    }
  `}</style>
);

const RobotAvatar = ({ size = 100 }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="game-avatar">
    <circle cx="50" cy="50" r="45" fill="#E0F2FE" stroke="#0EA5E9" strokeWidth="4"/>
    <rect x="25" y="35" width="50" height="35" rx="10" fill="#FFFFFF" stroke="#0EA5E9" strokeWidth="4"/>
    <circle cx="38" cy="50" r="6" fill="#0EA5E9"/>
    <circle cx="62" cy="50" r="6" fill="#0EA5E9"/>
    <path d="M40 70 Q50 80 60 70" stroke="#0EA5E9" strokeWidth="4" strokeLinecap="round"/>
    <line x1="50" y1="15" x2="50" y2="35" stroke="#0EA5E9" strokeWidth="4"/>
    <circle cx="50" cy="15" r="5" fill="#F59E0B"/>
  </svg>
);

export default function App() {
  const [view, setView] = useState<AppView>("login");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [globalMessage, setGlobalMessage] = useState("");
  const [appHeaderCollapsed, setAppHeaderCollapsed] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const token = getStoredAuthToken();
    if (!token) {
      setBooting(false);
      setView("login");
      return;
    }
    fetchCurrentUser()
      .then((response) => {
        setUser(response.user);
        setView("workbench");
      })
      .catch(() => {
        setStoredAuthToken(null);
        setUser(null);
        setView("login");
      })
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    if (!accountMenuOpen) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!accountMenuRef.current?.contains(event.target as Node)) setAccountMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAccountMenuOpen(false);
    };
    window.addEventListener("pointerdown", closeOnOutsideClick);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOnOutsideClick);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [accountMenuOpen]);

  useEffect(() => {
    setAccountMenuOpen(false);
  }, [appHeaderCollapsed, view]);

  async function handleLoggedIn(token: string, nextUser: AuthUser) {
    setStoredAuthToken(token);
    setUser(nextUser);
    setGlobalMessage("");
    setView("workbench");
  }

  async function handleLogout() {
    setAccountMenuOpen(false);
    try {
      await logout();
    } catch {
      // 本地退出优先，服务端会在 token 过期后自动失效。
    }
    setStoredAuthToken(null);
    setUser(null);
    setGlobalMessage("已退出登录。");
    setView("login");
  }

  if (booting) {
    return (
      <>
        <GameStyles />
        <main className="auth-page">
          <section className="auth-card compact">
            <RobotAvatar size={80} />
            <p className="eyebrow">AI Native Data Analysis Workbench</p>
            <h1>正在进入工作台</h1>
            <p>正在校验系统状态，即将开启数据探索旅程...</p>
          </section>
        </main>
      </>
    );
  }

  if (!user) {
    return (
      <>
        <GameStyles />
        {view === "register" ? (
          <RegisterPage onBack={() => setView("login")} onMessage={setGlobalMessage} globalMessage={globalMessage} />
        ) : (
          <LoginPage onRegister={() => setView("register")} onLoggedIn={handleLoggedIn} globalMessage={globalMessage} />
        )}
      </>
    );
  }

  return (
    <div className="app-shell">
      <GameStyles />
      <header className={`app-header ${appHeaderCollapsed ? "collapsed" : ""}`}>
        <button
          className="app-header-toggle"
          type="button"
          aria-expanded={!appHeaderCollapsed}
          aria-label={appHeaderCollapsed ? "展开顶部导航栏" : "收起顶部导航栏"}
          title={appHeaderCollapsed ? "展开顶部导航栏" : "收起顶部导航栏"}
          onClick={() => setAppHeaderCollapsed((value) => !value)}
        >
          <span aria-hidden="true" className="app-header-toggle-icon">
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
              <path d={appHeaderCollapsed ? "M7 10l5 5 5-5" : "M7 14l5-5 5 5"} />
            </svg>
          </span>
        </button>
        {!appHeaderCollapsed ? (
          <>
            <div className="app-title-block">
              <p className="eyebrow">AI Native Data Analysis Workbench</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <h1>DeepSeek 多 Agent 数据分析工作台</h1>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', background: '#E0F2FE', padding: '4px 12px', borderRadius: '20px', border: '1px solid #bae6fd' }}>
                  <span style={{ fontSize: '12px', color: '#0369A1', fontWeight: 'bold' }}>Lv. 1 数据探索者</span>
                  <div style={{ width: '80px', height: '6px', background: '#bae6fd', borderRadius: '3px', overflow: 'hidden' }}>
                    <div style={{ width: '45%', height: '100%', background: '#0EA5E9', animation: 'pulseGlow 2s infinite' }}></div>
                  </div>
                </div>
              </div>
            </div>
            <nav className="app-nav" aria-label="账号与系统导航">
              <button type="button" className={view === "workbench" ? "active" : ""} onClick={() => setView("workbench")}>
                工作台
              </button>
              <div className="account-menu" ref={accountMenuRef}>
                <button
                  type="button"
                  className={`account-menu-trigger ${view === "account" || view === "admin" || accountMenuOpen ? "active" : ""}`}
                  aria-haspopup="menu"
                  aria-expanded={accountMenuOpen}
                  onClick={() => setAccountMenuOpen((value) => !value)}
                >
                  {user.role === "admin" ? "系统管理员" : "个人账户"}
                </button>
                {accountMenuOpen ? (
                  <div className="account-dropdown" role="menu" aria-label="账户操作">
                    <div className="account-dropdown-profile">
                      <strong>{user.username}</strong>
                      <span>{roleLabel(user.role)} · {user.login_account}</span>
                    </div>
                    <button type="button" role="menuitem" className={view === "account" ? "current" : ""} onClick={() => { setView("account"); setAccountMenuOpen(false); }}>
                      <span>账号设置</span><small>资料与密码</small>
                    </button>
                    {user.role === "admin" ? (
                      <button type="button" role="menuitem" className={view === "admin" ? "current" : ""} onClick={() => { setView("admin"); setAccountMenuOpen(false); }}>
                        <span>用户管理</span><small>审核与权限</small>
                      </button>
                    ) : null}
                    <button type="button" role="menuitem" className="account-dropdown-logout" onClick={handleLogout}>
                      <span>退出登录</span><small>结束当前会话</small>
                    </button>
                  </div>
                ) : null}
              </div>
            </nav>
          </>
        ) : null}
      </header>

      <AppErrorBoundary resetKey={`${view}-${user.id}`}>
        {view === "workbench" ? <WorkbenchPage currentUser={user} /> : null}
        {view === "account" ? <AccountPage user={user} onUserChange={setUser} onLogout={handleLogout} /> : null}
        {view === "admin" && user.role === "admin" ? <AdminPage currentUser={user} /> : null}
      </AppErrorBoundary>
    </div>
  );
}

class AppErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  { error: Error | null; resetKey: string }
> {
  state = { error: null as Error | null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  static getDerivedStateFromProps(
    props: { resetKey: string },
    state: { error: Error | null; resetKey: string }
  ) {
    if (props.resetKey !== state.resetKey) {
      return { error: null, resetKey: props.resetKey };
    }
    return null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Workbench render error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="workspace-shell">
          <section className="panel render-error-panel">
            <h2>前端展示异常</h2>
            <p>当前分析结果中存在暂时无法展示的字段，页面已阻止白屏。请刷新或切换页面后继续查看。</p>
            <pre>{this.state.error.message}</pre>
            <button className="primary-button" type="button" onClick={() => this.setState({ error: null })}>
              重新显示页面
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function LoginPage({
  onRegister,
  onLoggedIn,
  globalMessage
}: {
  onRegister: () => void;
  onLoggedIn: (token: string, user: AuthUser) => void;
  globalMessage: string;
}) {
  const [loginAccount, setLoginAccount] = useState("admin");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(globalMessage);

  useEffect(() => {
    setMessage(globalMessage);
  }, [globalMessage]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("正在登录。");
    try {
      const response = await login(loginAccount, password);
      onLoggedIn(response.token, response.user);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <RobotAvatar />
        <p className="eyebrow">Data Quest</p>
        <h1>登录数据分析工作台</h1>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            登录账号
            <input value={loginAccount} onChange={(event) => setLoginAccount(event.target.value)} autoComplete="username" />
          </label>
          <label>
            密码
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "校验中" : "进入工作台"}
          </button>
        </form>
        {message ? <p className="auth-message">{message}</p> : null}
        <button className="link-button" type="button" style={{ marginTop: '16px', background: 'transparent', border: 'none', cursor: 'pointer', color: '#0ea5e9', fontWeight: 'bold' }} onClick={onRegister}>
          没有角色权限？申请注册账号
        </button>
      </section>
    </main>
  );
}

function RegisterPage({
  onBack,
  onMessage,
  globalMessage
}: {
  onBack: () => void;
  onMessage: (message: string) => void;
  globalMessage: string;
}) {
  const [loginAccount, setLoginAccount] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [registerReason, setRegisterReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(globalMessage);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("正在提交注册申请。");
    try {
      const response = await registerUser(loginAccount, username, password, registerReason);
      const nextMessage = `${response.message} 当前状态：${statusLabel(response.user.status)}。`;
      setMessage(nextMessage);
      onMessage(nextMessage);
      setLoginAccount("");
      setUsername("");
      setPassword("");
      setRegisterReason("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "注册失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <RobotAvatar size={80} />
        <p className="eyebrow">Data Quest</p>
        <h1>注册账号</h1>
        <p>注册后需等待管理员审核通过，方可建立角色信息。登录账号不可修改，用户名可后续调整。</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            登录账号
            <input value={loginAccount} onChange={(event) => setLoginAccount(event.target.value)} autoComplete="username" placeholder="例如 zhangsan" />
          </label>
          <label>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="显示在系统中的名称" />
          </label>
          <label>
            密码
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
          </label>
          <label>
            申请说明
            <textarea rows={4} value={registerReason} onChange={(event) => setRegisterReason(event.target.value)} placeholder="说明使用场景，便于管理员审核" />
          </label>
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "提交中" : "提交注册申请"}
          </button>
        </form>
        {message ? <p className="auth-message">{message}</p> : null}
        <button className="link-button" type="button" style={{ marginTop: '16px', background: 'transparent', border: 'none', cursor: 'pointer', color: '#0ea5e9', fontWeight: 'bold' }} onClick={onBack}>
          返回登录
        </button>
      </section>
    </main>
  );
}

function AccountPage({
  user,
  onUserChange,
  onLogout
}: {
  user: AuthUser;
  onUserChange: (user: AuthUser) => void;
  onLogout: () => void;
}) {
  const [username, setUsername] = useState(user.username);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await updateMyProfile(username);
      onUserChange(response.user);
      setProfileMessage("用户名已更新。");
    } catch (error) {
      setProfileMessage(error instanceof Error ? error.message : "用户名修改失败。");
    } finally {
      setLoading(false);
    }
  }

  async function handlePasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      await changeMyPassword(oldPassword, newPassword);
      setPasswordMessage("密码已修改，请重新登录。");
      setStoredAuthToken(null);
      window.setTimeout(() => onLogout(), 500);
    } catch (error) {
      setPasswordMessage(error instanceof Error ? error.message : "密码修改失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="settings-page" style={{ padding: '40px', maxWidth: '1000px', margin: '0 auto' }}>
      <section className="settings-card account-overview" style={{ marginBottom: '20px' }}>
        <div className="account-identity" style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          <span className="account-avatar" aria-hidden="true" style={{ width: '60px', height: '60px', background: '#0ea5e9', borderRadius: '50%', color: '#fff', display: 'grid', placeItems: 'center', fontSize: '24px', fontWeight: 'bold' }}>
            {(user.username || user.login_account).slice(0, 1).toUpperCase()}
          </span>
          <div>
            <p className="eyebrow">账号设置</p>
            <h2>{user.username}</h2>
            <span style={{ color: '#64748b' }}>登录账号 {user.login_account} 固定不可修改</span>
          </div>
        </div>
        <dl className="account-kv" style={{ display: 'flex', gap: '40px', marginTop: '20px' }}>
          <div>
            <dt style={{ color: '#64748b', fontSize: '13px' }}>登录账号</dt>
            <dd style={{ margin: 0, fontWeight: 'bold' }}>{user.login_account}</dd>
          </div>
          <div>
            <dt style={{ color: '#64748b', fontSize: '13px' }}>角色</dt>
            <dd style={{ margin: 0, fontWeight: 'bold' }}>{roleLabel(user.role)}</dd>
          </div>
          <div>
            <dt style={{ color: '#64748b', fontSize: '13px' }}>账号状态</dt>
            <dd style={{ margin: 0, fontWeight: 'bold' }}>{statusLabel(user.status)}</dd>
          </div>
        </dl>
      </section>

      <section className="account-action-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <form className="settings-card auth-form account-action-card" onSubmit={handleProfileSubmit}>
          <p className="eyebrow">资料</p>
          <h3>修改用户名</h3>
          <label style={{ display: 'block', marginBottom: '10px' }}>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <button className="primary-button" type="submit" disabled={loading}>
            保存用户名
          </button>
          {profileMessage ? <p className="auth-message">{profileMessage}</p> : null}
        </form>
        <form className="settings-card auth-form account-action-card" onSubmit={handlePasswordSubmit}>
          <p className="eyebrow">安全</p>
          <h3>修改密码</h3>
          <label style={{ display: 'block', marginBottom: '10px' }}>
            原密码
            <input type="password" value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} autoComplete="current-password" />
          </label>
          <label style={{ display: 'block', marginBottom: '10px' }}>
            新密码
            <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" />
          </label>
          <button className="primary-button" type="submit" disabled={loading} style={{ background: '#1e293b' }}>
            修改密码并重新登录
          </button>
          {passwordMessage ? <p className="auth-message">{passwordMessage}</p> : null}
        </form>
      </section>
    </main>
  );
}

function AdminPage({ currentUser }: { currentUser: AuthUser }) {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const pendingCount = useMemo(() => users.filter((item) => item.status === "pending").length, [users]);

  useEffect(() => {
    void refreshUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshUsers(nextStatus = statusFilter, nextQuery = query) {
    setLoading(true);
    try {
      const response = await fetchAdminUsers(nextStatus, nextQuery);
      setUsers(response.users);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取用户列表失败。");
    } finally {
      setLoading(false);
    }
  }

  async function runUserAction(action: () => Promise<unknown>, successMessage: string) {
    setLoading(true);
    setMessage("正在处理用户操作。");
    try {
      await action();
      setMessage(successMessage);
      await refreshUsers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "用户操作失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="settings-page" style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <section className="settings-card" style={{ marginBottom: '20px' }}>
        <div className="section-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>管理员用户管理</h2>
          <span style={{ background: '#E0F2FE', padding: '4px 12px', borderRadius: '20px', color: '#0369A1', fontWeight: 'bold' }}>
            {pendingCount ? `${pendingCount} 个待审核账号` : "无待审核账号"}
          </span>
        </div>
        <div className="admin-toolbar" style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} style={{ width: '150px' }}>
            <option value="">全部状态</option>
            <option value="pending">待审核</option>
            <option value="active">正常</option>
            <option value="frozen">冻结</option>
            <option value="rejected">已驳回</option>
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索账号或用户名" style={{ flex: 1 }} />
          <button className="primary-button" type="button" disabled={loading} onClick={() => refreshUsers()} style={{ width: '120px' }}>
            查询
          </button>
        </div>
        {message ? <p className="auth-message" style={{ marginTop: '15px' }}>{message}</p> : null}
      </section>

      <section className="settings-card">
        <div className="admin-user-table-wrap" style={{ overflowX: 'auto' }}>
          <table className="admin-user-table" style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                <th style={{ padding: '12px 8px' }}>登录账号</th>
                <th style={{ padding: '12px 8px' }}>用户名</th>
                <th style={{ padding: '12px 8px' }}>角色</th>
                <th style={{ padding: '12px 8px' }}>状态</th>
                <th style={{ padding: '12px 8px' }}>最近登录</th>
                <th style={{ padding: '12px 8px' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => {
                const isSelf = item.id === currentUser.id;
                return (
                  <tr key={item.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                    <td style={{ padding: '12px 8px' }}>{item.login_account}</td>
                    <td style={{ padding: '12px 8px' }}>{item.username}</td>
                    <td style={{ padding: '12px 8px' }}>{roleLabel(item.role)}</td>
                    <td style={{ padding: '12px 8px' }}>{statusLabel(item.status)}</td>
                    <td style={{ padding: '12px 8px' }}>{item.last_login_at ? new Date(item.last_login_at).toLocaleString() : "-"}</td>
                    <td style={{ padding: '12px 8px' }}>
                      <div className="admin-actions" style={{ display: 'flex', gap: '8px' }}>
                        {item.status === "pending" ? (
                          <>
                            <button type="button" style={{ background: '#10b981', color: '#fff', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer' }} onClick={() => runUserAction(() => reviewAdminUser(item.id, "approve", "管理员审核通过。"), "账号已通过审核。")}>
                              通过
                            </button>
                            <button type="button" style={{ background: '#ef4444', color: '#fff', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer' }} onClick={() => runUserAction(() => reviewAdminUser(item.id, "reject", "管理员驳回注册申请。"), "账号申请已驳回。")}>
                              驳回
                            </button>
                          </>
                        ) : null}
                        {item.status === "active" && !isSelf ? (
                          <button type="button" style={{ background: '#f59e0b', color: '#fff', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer' }} onClick={() => runUserAction(() => freezeAdminUser(item.id, true, "管理员冻结账号。"), "账号已冻结。")}>
                            冻结
                          </button>
                        ) : null}
                        {item.status === "frozen" ? (
                          <button type="button" style={{ background: '#0ea5e9', color: '#fff', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer' }} onClick={() => runUserAction(() => freezeAdminUser(item.id, false, "管理员解除冻结。"), "账号已解冻。")}>
                            解冻
                          </button>
                        ) : null}
                        {item.status === "active" && !isSelf ? (
                          <button type="button" style={{ background: '#64748b', color: '#fff', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer' }} onClick={() => runUserAction(() => changeAdminUserRole(item.id, item.role === "admin" ? "user" : "admin"), "角色已更新。")}>
                            设为{item.role === "admin" ? "用户" : "管理员"}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!users.length ? (
                <tr>
                  <td colSpan={6} style={{ padding: '20px', textAlign: 'center', color: '#64748b' }}>暂无用户记录。</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function roleLabel(role: string) {
  return role === "admin" ? "管理员" : "普通用户";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "待审核",
    active: "正常",
    frozen: "已冻结",
    rejected: "已驳回"
  };
  return labels[status] || status;
}