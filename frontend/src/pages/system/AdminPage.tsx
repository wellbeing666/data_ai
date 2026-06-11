import { ReloadOutlined, SearchOutlined, UserSwitchOutlined } from "@ant-design/icons";
import { Button, Card, Input, Select, Space, Table, Tag, Typography, type TableColumnsType } from "antd";
import { useEffect, useMemo, useState } from "react";

import { changeAdminUserRole, fetchAdminUsers, freezeAdminUser, reviewAdminUser } from "../../api";
import { roleLabel, statusLabel } from "../../navigation";
import type { AuthUser } from "../../types";

const statusColors: Record<string, string> = {
  pending: "gold",
  active: "green",
  frozen: "red",
  rejected: "default"
};

export function AdminPage({ currentUser }: { currentUser: AuthUser }) {
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

  async function runAction(action: () => Promise<unknown>, successMessage: string) {
    setLoading(true);
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

  const columns: TableColumnsType<AuthUser> = [
    {
      title: "登录账号",
      dataIndex: "login_account",
      fixed: "left",
      width: 160,
      render: (value: string, record) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary" className="dense-secondary">{record.username}</Typography.Text>
        </Space>
      )
    },
    {
      title: "角色",
      dataIndex: "role",
      width: 110,
      render: (value: string) => <Tag color={value === "admin" ? "blue" : "default"}>{roleLabel(value)}</Tag>
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: (value: string) => <Tag color={statusColors[value] || "default"}>{statusLabel(value)}</Tag>
    },
    {
      title: "最近登录",
      dataIndex: "last_login_at",
      width: 180,
      render: (value?: string | null) => value ? new Date(value).toLocaleString() : "-"
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 260,
      render: (_, item) => {
        const isSelf = item.id === currentUser.id;
        return (
          <Space size={4} wrap>
            {item.status === "pending" ? (
              <>
                <Button size="small" type="link" onClick={() => runAction(() => reviewAdminUser(item.id, "approve", "管理员审核通过。"), "账号已通过审核。")}>通过</Button>
                <Button size="small" type="link" danger onClick={() => runAction(() => reviewAdminUser(item.id, "reject", "管理员驳回注册申请。"), "账号申请已驳回。")}>驳回</Button>
              </>
            ) : null}
            {item.status === "active" && !isSelf ? (
              <Button size="small" type="link" danger onClick={() => runAction(() => freezeAdminUser(item.id, true, "管理员冻结账号。"), "账号已冻结。")}>冻结</Button>
            ) : null}
            {item.status === "frozen" ? (
              <Button size="small" type="link" onClick={() => runAction(() => freezeAdminUser(item.id, false, "管理员解冻账号。"), "账号已解冻。")}>解冻</Button>
            ) : null}
            {item.status === "active" && !isSelf ? (
              <Button size="small" type="link" onClick={() => runAction(() => changeAdminUserRole(item.id, item.role === "admin" ? "user" : "admin"), "角色已更新。")}>
                设为{item.role === "admin" ? "普通用户" : "管理员"}
              </Button>
            ) : null}
          </Space>
        );
      }
    }
  ];

  return (
    <div className="workspace">
      <Card className="operation-card admin-table-card" variant="outlined">
        <div className="admin-page-header">
          <div>
            <p className="eyebrow">系统管理</p>
            <h2>用户管理</h2>
            <p>集中处理审核、冻结、解冻和角色调整。</p>
          </div>
          <Space wrap>
            <Tag color="gold">{pendingCount} 个待审核</Tag>
            <Tag color="blue"><UserSwitchOutlined /> {users.length} 个账号</Tag>
          </Space>
        </div>
        <div className="admin-filterbar">
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 150 }}
            options={[
              { value: "", label: "全部状态" },
              { value: "pending", label: "待审核" },
              { value: "active", label: "正常" },
              { value: "frozen", label: "冻结" },
              { value: "rejected", label: "已驳回" }
            ]}
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onPressEnter={() => refreshUsers()}
            prefix={<SearchOutlined />}
            placeholder="搜索账号或用户名"
            className="admin-search-input"
          />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={() => refreshUsers()}>查询</Button>
          <Button icon={<ReloadOutlined />} disabled={loading} onClick={() => refreshUsers("", "")}>重置</Button>
        </div>
        {message ? <p className="notice">{message}</p> : null}
        <Table
          rowKey="id"
          className="dense-ant-table"
          size="small"
          columns={columns}
          dataSource={users}
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          scroll={{ x: 920 }}
        />
      </Card>
    </div>
  );
}
