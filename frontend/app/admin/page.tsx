"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DocumentUpload } from "@/components/DocumentUpload";

export default function AdminPage() {
  const [stats, setStats] = useState<any>(null);
  const [docs, setDocs] = useState<any[]>([]);

  const refresh = () => {
    api.stats().then(setStats).catch(() => {});
    api.documents().then(setDocs).catch(() => {});
  };
  useEffect(refresh, []);

  return (
    <main style={{ maxWidth: 900, margin: "0 auto" }}>
      <h1 style={{ fontSize: 18, fontWeight: 500 }}>Administration</h1>

      {stats && (
        <div style={{ display: "flex", gap: 24, margin: "16px 0 32px", fontSize: 14 }}>
          <div><strong>{stats.documents}</strong> documents</div>
          <div><strong>{stats.queries}</strong> queries</div>
          {/* A spike here usually means a filter bug, not a corpus gap. */}
          <div><strong>{stats.zero_result_queries}</strong> zero-result</div>
          <div><strong>{stats.ungrounded_answers}</strong> ungrounded</div>
        </div>
      )}

      <h2 style={{ fontSize: 15, fontWeight: 500 }}>Upload</h2>
      <DocumentUpload onDone={refresh} />

      <h2 style={{ fontSize: 15, fontWeight: 500, marginTop: 32 }}>Documents</h2>
      <table style={{ width: "100%", fontSize: 14, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #d5d3cb" }}>
            <th>File</th><th>Readable by</th><th>Clearance</th><th>Status</th><th>Chunks</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id} style={{ borderBottom: "1px solid #ece9e2" }}>
              <td>{d.filename}</td>
              <td>{(d.allowed_roles ?? []).join(", ")}</td>
              <td>{d.min_clearance}</td>
              {/* Status matters: a document stuck in "pending" is invisible to
                  search, and users will report it as missing data. */}
              <td>{d.status}</td>
              <td>{d.chunk_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
