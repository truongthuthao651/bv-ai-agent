import { useEffect, useState } from "react";
import { Card, Table, Tag } from "../components/index.js";
import { localizedRoleLabel } from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { fetchAccounts } from "./api.js";

export function UsersView() {
  const { t } = useLocale();
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
          {t("users.title")}
        </h1>
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--text-md)" }}>{t("users.description")}</p>
      </div>

      <Card title={t("users.cardTitle")} hint={t("users.cardHint")} size="lg">
        {error ? (
          <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--danger)" }}>
            {t("admin.loadListError")} {error}
          </p>
        ) : (
          <Table
            columns={[t("common.email"), t("common.role")]}
            rows={accounts}
            emptyLabel={t("users.empty")}
            renderRow={(a) => [a.email, <Tag key="role">{localizedRoleLabel(a.role, t) || a.role}</Tag>]}
          />
        )}
      </Card>
    </div>
  );
}
