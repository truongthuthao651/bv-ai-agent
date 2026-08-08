import { useState } from "react";
import {
  Badge,
  Tag,
  Button,
  ChatBubble,
  ChatComposer,
  PromptSuggestion,
  KpiCard,
  StatusPill,
  Table,
  StatTile,
  Modal,
  Input,
  Select,
  Textarea,
  Dropzone,
  Card,
} from "../components/index.js";

function Section({ label, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div
        style={{
          fontSize: "var(--text-2xs)",
          fontWeight: "var(--weight-bold)",
          textTransform: "uppercase",
          letterSpacing: "var(--tracking-wide)",
          color: "var(--text-muted)",
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

const DOCS = [
  { title: "Quy tắc An Bình Ưu Việt", type: "policy" },
  { title: "Quy trình giải quyết quyền lợi", type: "procedure" },
];

export function ComponentGallery() {
  const [chatValue, setChatValue] = useState("");
  const [inputValue, setInputValue] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
      <Section label="Buttons">
        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <Button variant="primary">Primary</Button>
          <Button variant="accent">Accent</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
      </Section>

      <Section label="Badges & tags">
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", alignItems: "center" }}>
          <Badge label="Ollama: Hoạt động" status="ok" />
          <Badge label="Qdrant: Ngừng" status="bad" />
          <Badge label="Đang kiểm tra…" status="neutral" />
          <Tag>policy</Tag>
          <Tag tone="muted">Có căn cứ: 12</Tag>
        </div>
      </Section>

      <Section label="Dashboard: KPI & status">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--gap-card)" }}>
          <KpiCard label="Questions today" value="1,284" delta={12} trend={[0.2, 0.3, 0.35, 0.5, 0.4, 0.6, 0.8]} />
          <KpiCard
            label="Typical answer time"
            value="1.8"
            unit="s"
            delta={-6}
            betterWhen="down"
            trend={[0.7, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35]}
          />
          <KpiCard label="Rated helpful" value="91" unit="%" delta={-3} trend={[0.94, 0.93, 0.9, 0.92, 0.89, 0.9, 0.87]} />
        </div>
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
          <StatusPill status="indexed" label="Indexed" />
          <StatusPill status="processing" label="Processing" />
          <StatusPill status="failed" label="Failed" />
          <StatusPill status="queued" label="Queued" />
        </div>
      </Section>

      <Section label="Table & stat tiles">
        <Table columns={["Tên tài liệu", "Loại"]} rows={DOCS} renderRow={(d) => [d.title, <Tag key={d.title}>{d.type}</Tag>]} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "var(--gap-card)" }}>
          <StatTile value="128" label="Số câu hỏi" />
          <StatTile value="1.8s" label="Độ trễ trung vị (p50)" />
        </div>
      </Section>

      <Section label="Form controls">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 420 }}>
          <Dropzone hint=".md · .docx · .xlsx · .pdf" />
          <Input value={inputValue} onChange={(e) => setInputValue(e.target.value)} placeholder="Tên tài liệu" />
          <Select>
            <option>Loại tài liệu</option>
          </Select>
          <Textarea rows={2} placeholder="Ví dụ: Phí thuần là gì?" />
        </div>
      </Section>

      <Section label="Card">
        <Card title="Tài liệu đã nạp" hint="Danh sách tài liệu hiện có trong Qdrant.">
          <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>Nội dung card ở đây.</p>
        </Card>
      </Section>

      <Section label="Modal">
        <Button variant="secondary" onClick={() => setModalOpen(true)}>
          Open modal
        </Button>
        <Modal
          open={modalOpen}
          title="Sửa tài liệu"
          hint="Chỉnh sửa tên, loại, phòng ban…"
          onClose={() => setModalOpen(false)}
          actions={
            <>
              <Button variant="secondary" onClick={() => setModalOpen(false)}>
                Huỷ
              </Button>
              <Button variant="primary" onClick={() => setModalOpen(false)}>
                Lưu
              </Button>
            </>
          }
        >
          <Input placeholder="Tên tài liệu" />
        </Modal>
      </Section>

      <Section label="Chat primitives">
        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <PromptSuggestion eyebrow="Giải thích thuật ngữ" title="Phí thuần là gì?" />
          <PromptSuggestion eyebrow="Tra cứu công thức" title="Dự phòng toán học" />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          <ChatBubble role="user">Phí thuần là gì?</ChatBubble>
          <ChatBubble role="assistant">
            Phí thuần (net premium) là phần phí bảo hiểm dùng để chi trả quyền lợi, không bao gồm chi phí quản lý. [1]
          </ChatBubble>
        </div>
        <ChatComposer value={chatValue} onChange={(e) => setChatValue(e.target.value)} placeholder="Nhập câu hỏi…" />
      </Section>
    </div>
  );
}
