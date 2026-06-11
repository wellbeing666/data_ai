import { type FormEvent, useState } from "react";

import { changeMyPassword, setStoredAuthToken, updateMyProfile } from "../../api";
import { roleLabel, statusLabel } from "../../navigation";
import type { AuthUser } from "../../types";

export function AccountPage({
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
    <div className="workspace">
      <div className="content-grid two">
        <section className="card">
          <div className="card-header">
            <div>
              <h2>账号资料</h2>
              <p>查看账号状态和基础权限。</p>
            </div>
            <span className="badge badge-secondary">{roleLabel(user.role)}</span>
          </div>
          <div className="kv-list">
            <div><span>登录账号</span><strong>{user.login_account}</strong></div>
            <div><span>用户状态</span><strong>{statusLabel(user.status)}</strong></div>
            <div><span>最近登录</span><strong>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "-"}</strong></div>
          </div>
        </section>
        <section className="card">
          <div className="card-header">
            <div>
              <h2>修改用户名</h2>
              <p>登录账号固定，展示名称可以调整。</p>
            </div>
          </div>
          <form className="form-stack" onSubmit={handleProfileSubmit}>
            <label>
              用户名
              <input value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <button className="button button-primary" type="submit" disabled={loading}>保存用户名</button>
          </form>
          {profileMessage ? <p className="notice">{profileMessage}</p> : null}
        </section>
        <section className="card span-two">
          <div className="card-header">
            <div>
              <h2>修改密码</h2>
              <p>修改后会自动退出，需要重新登录。</p>
            </div>
          </div>
          <form className="inline-form" onSubmit={handlePasswordSubmit}>
            <label>
              原密码
              <input type="password" value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} />
            </label>
            <label>
              新密码
              <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
            </label>
            <button className="button button-outline" type="submit" disabled={loading}>修改密码</button>
          </form>
          {passwordMessage ? <p className="notice">{passwordMessage}</p> : null}
        </section>
      </div>
    </div>
  );
}
