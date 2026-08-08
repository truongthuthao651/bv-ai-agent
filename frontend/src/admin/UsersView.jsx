import { useEffect, useState } from "react";
import { Card, Table, Tag } from "../components/index.js";
import { fetchAccounts } from "./api.js";

const ROLE_LABEL = { admin: "Quản trị viên", employee: "Nhân viên" };

export function UsersView() {
  const [accounts, setAccounts] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAccounts()
      .then(setAccounts)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
      <div>
        <h1 style={{ fontSize: "var(--text-3xl)", fontWeight: "var(--weight-heavy)", letterSpacing: "var(--tracking-tight)", color: "var(--text-primary)", margin: "0 0 var(--space-2)", lineHeight: "var(--leading-tight)" }}>
          Người dùng
        </h1>
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--text-md)" }}>
          Tài khoản đăng nhập trang quản trị (email @baoviet.com).
        </p>
      </div>

      <Card
        title="Tài khoản đã cấp"
        hint="Chỉ xem — chưa có tạo/xoá tài khoản qua giao diện, dùng scripts/seed_accounts.py trên máy chủ."
        size="lg"
      >
        {error ? (
          <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--danger)" }}>Không tải được danh sách: {error}</p>
        ) : (
          <Table
            columns={["Email", "Vai trò"]}
            rows={accounts}
            emptyLabel="Chưa có tài khoản nào."
            renderRow={(a) => [a.email, <Tag key="role">{ROLE_LABEL[a.role] || a.role}</Tag>]}
          />
        )}
      </Card>
    </div>
  );
}
