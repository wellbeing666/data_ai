import { type FormEvent, useState } from "react";

import { registerUser } from "../../api";
import { AuthFormCard, AuthFrame } from "../../components/auth/AuthLayout";
import { statusLabel } from "../../navigation";

export function RegisterPage({
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
    try {
      const response = await registerUser(loginAccount, username, password, registerReason);
      const nextMessage = `${response.message} 当前状态：${statusLabel(response.user.status)}`;
      setMessage(nextMessage);
      onMessage(nextMessage);
      setLoginAccount("");
      setUsername("");
      setPassword("");
      setRegisterReason("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "注册申请提交失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame>
      <AuthFormCard
        eyebrow="账户申请"
        title="注册工作台账号"
        description="提交申请后需要管理员审核，通过后才能进入分析工作台。"
        wide
      >
        <form className="form-stack" onSubmit={handleSubmit}>
          <label>
            登录账号
            <input value={loginAccount} onChange={(event) => setLoginAccount(event.target.value)} autoComplete="username" />
          </label>
          <label>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            密码
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
          </label>
          <label>
            申请说明
            <textarea rows={4} value={registerReason} onChange={(event) => setRegisterReason(event.target.value)} />
          </label>
          <button className="button button-primary full" type="submit" disabled={loading}>
            {loading ? "正在提交" : "提交注册申请"}
          </button>
        </form>
        {message ? <p className="notice">{message}</p> : null}
        <button className="button button-ghost full" type="button" onClick={onBack}>
          返回登录
        </button>
      </AuthFormCard>
    </AuthFrame>
  );
}
