import { menuSections, roleLabel, statusLabel, type AppPageKey } from "../navigation";
import type { AuthUser } from "../types";

export function AppSidebar({
  user,
  activePage,
  onPageChange,
  onLogout
}: {
  user: AuthUser;
  activePage: AppPageKey;
  onPageChange: (page: AppPageKey) => void;
  onLogout: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark">AI</span>
        <div>
          <strong>AI 数据工作台</strong>
        </div>
      </div>
      <nav className="sidebar-nav grouped" aria-label="主导航">
        {menuSections.map((section) => {
          const items = section.items.filter((item) => !item.adminOnly || user.role === "admin");
          if (!items.length) return null;
          return (
            <div className="sidebar-section" key={section.title}>
              <p>{section.title}</p>
              {items.map((item) => (
                <button
                  className={activePage === item.key ? "active" : ""}
                  type="button"
                  key={item.key}
                  onClick={() => onPageChange(item.key)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {item.label}
                </button>
              ))}
            </div>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <div className="user-card">
          <span className="avatar">{user.username.slice(0, 1).toUpperCase()}</span>
          <div>
            <strong>{user.username}</strong>
            <span>{user.login_account}</span>
          </div>
        </div>
        <div className="user-meta">
          <span className="badge badge-secondary">{roleLabel(user.role)}</span>
          <span className="badge badge-outline">{statusLabel(user.status)}</span>
        </div>
        <button className="button button-outline full" type="button" onClick={onLogout}>
          退出登录
        </button>
      </div>
    </aside>
  );
}
