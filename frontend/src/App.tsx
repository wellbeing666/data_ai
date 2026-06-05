import { type FormEvent, useEffect, useMemo, useState } from "react";

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

export default function App() {
  const [view, setView] = useState<AppView>("login");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [globalMessage, setGlobalMessage] = useState("");

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

  async function handleLoggedIn(token: string, nextUser: AuthUser) {
    setStoredAuthToken(token);
    setUser(nextUser);
    setGlobalMessage("");
    setView("workbench");
  }

  async function handleLogout() {
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
      <main className="auth-page">
        <section className="auth-card compact">
          <p className="eyebrow">AI Native Data Analysis Workbench</p>
          <h1>正在进入工作台</h1>
          <p>正在校验登录状态，请稍候。</p>
        </section>
      </main>
    );
  }

  if (!user) {
    return view === "register" ? (
      <RegisterPage onBack={() => setView("login")} onMessage={setGlobalMessage} globalMessage={globalMessage} />
    ) : (
      <LoginPage onRegister={() => setView("register")} onLoggedIn={handleLoggedIn} globalMessage={globalMessage} />
    );
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">AI Native Data Analysis Workbench</p>
          <h1>DeepSeek 多 Agent 数据分析工作台</h1>
        </div>
        <nav className="app-nav" aria-label="账号与系统导航">
          <button type="button" className={view === "workbench" ? "active" : ""} onClick={() => setView("workbench")}>
            工作台
          </button>
          <button type="button" className={view === "account" ? "active" : ""} onClick={() => setView("account")}>
            账号设置
          </button>
          {user.role === "admin" ? (
            <button type="button" className={view === "admin" ? "active" : ""} onClick={() => setView("admin")}>
              用户管理
            </button>
          ) : null}
          <span className="user-badge">
            {user.username} · {roleLabel(user.role)}
          </span>
          <button type="button" onClick={handleLogout}>
            退出
          </button>
        </nav>
      </header>

      {view === "workbench" ? <WorkbenchPage /> : null}
      {view === "account" ? <AccountPage user={user} onUserChange={setUser} onLogout={handleLogout} /> : null}
      {view === "admin" && user.role === "admin" ? <AdminPage currentUser={user} /> : null}
    </div>
  );
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
        <p className="eyebrow">AI Native Data Analysis Workbench</p>
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
            {loading ? "登录中" : "登录"}
          </button>
        </form>
        {message ? <p className="auth-message">{message}</p> : null}
        <button className="link-button" type="button" onClick={onRegister}>
          没有账号？提交注册申请
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
        <p className="eyebrow">AI Native Data Analysis Workbench</p>
        <h1>注册账号</h1>
        <p>注册后需等待管理员审核通过，才能进入工作台。登录账号不可修改，用户名可后续调整。</p>
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
        <button className="link-button" type="button" onClick={onBack}>
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
    <main className="settings-page">
      <section className="settings-card">
        <div className="section-heading">
          <h2>账号设置</h2>
          <span>{user.login_account}</span>
        </div>
        <dl className="account-kv">
          <div>
            <dt>登录账号</dt>
            <dd>{user.login_account}（固定不可修改）</dd>
          </div>
          <div>
            <dt>角色</dt>
            <dd>{roleLabel(user.role)}</dd>
          </div>
          <div>
            <dt>账号状态</dt>
            <dd>{statusLabel(user.status)}</dd>
          </div>
        </dl>
      </section>

      <section className="settings-card two-column">
        <form className="auth-form" onSubmit={handleProfileSubmit}>
          <h3>修改用户名</h3>
          <label>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <button className="primary-button" type="submit" disabled={loading}>
            保存用户名
          </button>
          {profileMessage ? <p className="auth-message">{profileMessage}</p> : null}
        </form>
        <form className="auth-form" onSubmit={handlePasswordSubmit}>
          <h3>修改密码</h3>
          <label>
            原密码
            <input type="password" value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} autoComplete="current-password" />
          </label>
          <label>
            新密码
            <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" />
          </label>
          <button className="secondary-button" type="submit" disabled={loading}>
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
    <main className="settings-page">
      <section className="settings-card">
        <div className="section-heading">
          <h2>管理员用户管理</h2>
          <span>{pendingCount ? `${pendingCount} 个待审核账号` : "无待审核账号"}</span>
        </div>
        <div className="admin-toolbar">
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">全部状态</option>
            <option value="pending">待审核</option>
            <option value="active">正常</option>
            <option value="frozen">冻结</option>
            <option value="rejected">已驳回</option>
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索账号或用户名" />
          <button className="primary-button" type="button" disabled={loading} onClick={() => refreshUsers()}>
            查询
          </button>
        </div>
        {message ? <p className="auth-message">{message}</p> : null}
      </section>

      <section className="settings-card">
        <div className="admin-user-table-wrap">
          <table className="admin-user-table">
            <thead>
              <tr>
                <th>登录账号</th>
                <th>用户名</th>
                <th>角色</th>
                <th>状态</th>
                <th>最近登录</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => {
                const isSelf = item.id === currentUser.id;
                return (
                  <tr key={item.id}>
                    <td>{item.login_account}</td>
                    <td>{item.username}</td>
                    <td>{roleLabel(item.role)}</td>
                    <td>{statusLabel(item.status)}</td>
                    <td>{item.last_login_at ? new Date(item.last_login_at).toLocaleString() : "-"}</td>
                    <td>
                      <div className="admin-actions">
                        {item.status === "pending" ? (
                          <>
                            <button type="button" onClick={() => runUserAction(() => reviewAdminUser(item.id, "approve", "管理员审核通过。"), "账号已通过审核。")}>
                              通过
                            </button>
                            <button type="button" onClick={() => runUserAction(() => reviewAdminUser(item.id, "reject", "管理员驳回注册申请。"), "账号申请已驳回。")}>
                              驳回
                            </button>
                          </>
                        ) : null}
                        {item.status === "active" && !isSelf ? (
                          <button type="button" onClick={() => runUserAction(() => freezeAdminUser(item.id, true, "管理员冻结账号。"), "账号已冻结。")}>
                            冻结
                          </button>
                        ) : null}
                        {item.status === "frozen" ? (
                          <button type="button" onClick={() => runUserAction(() => freezeAdminUser(item.id, false, "管理员解除冻结。"), "账号已解冻。")}>
                            解冻
                          </button>
                        ) : null}
                        {item.status === "active" && !isSelf ? (
                          <button type="button" onClick={() => runUserAction(() => changeAdminUserRole(item.id, item.role === "admin" ? "user" : "admin"), "角色已更新。")}>
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
                  <td colSpan={6}>暂无用户记录。</td>
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
