"use client";

// A persistent badge showing the acting role. When someone is surprised by an
// answer, the first question is "as whom did I ask this?" — the UI should have
// answered it already.
export function RoleBadge({ role, clearance }: { role: string; clearance: number }) {
  return (
    <span
      title={`Answers are drawn only from documents visible to ${role}`}
      style={{
        display: "inline-flex", gap: 8, alignItems: "center",
        padding: "4px 10px", borderRadius: 999,
        border: "1px solid #d5d3cb", fontSize: 13,
      }}
    >
      <strong>{role}</strong>
      <span style={{ color: "#6f6e69" }}>clearance {clearance}</span>
    </span>
  );
}
