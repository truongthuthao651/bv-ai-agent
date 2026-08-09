import { useMemo, useState } from "react";
import { Button, Select } from "../index.js";
import { Table } from "./Table.jsx";

const PAGE_SIZE = 25;

function compareValues(a, b, dir) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return dir * (a - b);
  return dir * String(a).localeCompare(String(b));
}

/** Client-side filter, sort, and pagination over an in-memory row list. */
export function PaginatedList({
  rows,
  columns,
  renderRow,
  emptyLabel,
  getSortValue,
  defaultSortKey = "ts",
  defaultSortDir = "desc",
  filterPlaceholder,
  filterFn,
  extraFilters,
  rowKey = (row, i) => i,
}) {
  const [page, setPage] = useState(0);
  const [sortDir, setSortDir] = useState(defaultSortDir);
  const [query, setQuery] = useState("");

  const processed = useMemo(() => {
    let list = rows.slice();
    const q = query.trim().toLowerCase();
    if (q && filterFn) list = list.filter((row) => filterFn(row, q));
    if (extraFilters?.apply) list = extraFilters.apply(list);
    list.sort((a, b) => compareValues(getSortValue(a, defaultSortKey), getSortValue(b, defaultSortKey), sortDir === "asc" ? 1 : -1));
    return list;
  }, [rows, query, filterFn, extraFilters, sortDir, getSortValue, defaultSortKey]);

  const pageCount = Math.max(1, Math.ceil(processed.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = processed.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const toolbarStyle = {
    display: "flex",
    flexWrap: "wrap",
    gap: "var(--space-2)",
    alignItems: "center",
    marginBottom: "var(--space-4)",
  };

  return (
    <div>
      <div style={toolbarStyle}>
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          placeholder={filterPlaceholder}
          style={{
            flex: "1 1 180px",
            minWidth: 140,
            height: "var(--control-h-sm)",
            padding: "0 var(--pad-control-x)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border)",
            background: "var(--surface)",
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-sm)",
          }}
        />
        <Select
          size="sm"
          value={sortDir}
          onChange={(e) => {
            setSortDir(e.target.value);
            setPage(0);
          }}
          style={{ width: "auto", minWidth: 148 }}
        >
          <option value="desc">{extraFilters?.sortNewest ?? "Newest"}</option>
          <option value="asc">{extraFilters?.sortOldest ?? "Oldest"}</option>
        </Select>
        {extraFilters?.hours != null && (
          <Select
            size="sm"
            value={String(extraFilters.hours)}
            onChange={(e) => {
              extraFilters.onHours(Number(e.target.value));
              setPage(0);
            }}
            style={{ width: "auto", minWidth: 132 }}
          >
            {extraFilters.hourOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        )}
        {extraFilters?.mode != null && (
          <Select
            size="sm"
            value={extraFilters.mode}
            onChange={(e) => {
              extraFilters.onMode(e.target.value);
              setPage(0);
            }}
            style={{ width: "auto", minWidth: 120 }}
          >
            {extraFilters.modeOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        )}
        {extraFilters?.model != null && (
          <Select
            size="sm"
            value={extraFilters.model}
            onChange={(e) => {
              extraFilters.onModel(e.target.value);
              setPage(0);
            }}
            style={{ width: "auto", minWidth: 140 }}
          >
            {extraFilters.modelOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        )}
      </div>

      <Table columns={columns} rows={pageRows} renderRow={renderRow} emptyLabel={emptyLabel} rowKey={rowKey} />

      {processed.length > PAGE_SIZE && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--space-3)",
            marginTop: "var(--space-4)",
            fontSize: "var(--text-xs)",
            color: "var(--text-secondary)",
          }}
        >
          <span>
            {extraFilters?.pageLabel ?? "Page"} {safePage + 1} {extraFilters?.ofLabel ?? "of"} {pageCount}
            {" · "}
            {processed.length} {extraFilters?.rowsLabel ?? "rows"}
          </span>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button variant="secondary" size="sm" disabled={safePage <= 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
              {extraFilters?.prevLabel ?? "Prev"}
            </Button>
            <Button variant="secondary" size="sm" disabled={safePage >= pageCount - 1} onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}>
              {extraFilters?.nextLabel ?? "Next"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
