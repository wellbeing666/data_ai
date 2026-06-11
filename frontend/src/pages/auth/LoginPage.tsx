import { type FormEvent, useEffect, useState } from "react";

import { login } from "../../api";
import { AuthFormCard, AuthFrame } from "../../components/auth/AuthLayout";
import type { AuthUser } from "../../types";

export function LoginPage({
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

  useEffect(() => setMessage(globalMessage), [globalMessage]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("正在登录...");
    try {
      const response = await login(loginAccount, password);
      onLoggedIn(response.token, response.user);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame>
      <AuthFormCard
        title="登录数据分析工作台"
        description="使用账号进入数据分析后台。"
      >
        <form className="form-stack" onSubmit={handleSubmit}>
          <label>
            登录账号
            <input value={loginAccount} onChange={(event) => setLoginAccount(event.target.value)} autoComplete="username" />
          </label>
          <label>
            密码
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          <button className="button button-primary full" type="submit" disabled={loading}>
            {loading ? "正在登录" : "登录"}
          </button>
        </form>
        {message ? <p className="notice">{message}</p> : null}
        <button className="button button-ghost full" type="button" onClick={onRegister}>
          没有账号？提交注册申请
        </button>
      </AuthFormCard>
    </AuthFrame>
  );
}
