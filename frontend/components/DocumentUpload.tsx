"use client";

import { useState } from "react";

// The classification selector has NO default. A default of "All roles" is how
// documents become accidentally public; a required field costs the admin two
// seconds and removes an entire failure mode.
const ROLES = ["Admin", "HR", "Engineering", "Intern"];

export function DocumentUpload({ onDone }: { onDone?: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [clearance, setClearance] = useState(0);
  const [status, setStatus] = useState<string | null>(null);

  const canSubmit = !!file && roles.length > 0;

  async function submit() {
    if (!canSubmit) return;
    const fd = new FormData();
    fd.append("file", file!);
    fd.append("allowed_roles", roles.join(","));
    fd.append("min_clearance", String(clearance));

    setStatus("uploading…");
    const res = await fetch("/api/proxy/documents", {
      method: "POST", body: fd, credentials: "include",
    });
    setStatus(res.ok ? "indexed" : `failed: ${await res.text()}`);
    if (res.ok) onDone?.();
  }

  return (
    <div style={{ display: "grid", gap: 12, maxWidth: 460 }}>
      <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />

      <fieldset style={{ border: "1px solid #d5d3cb", borderRadius: 8, padding: 12 }}>
        <legend style={{ fontSize: 13 }}>Who may read this? (required)</legend>
        {ROLES.map((r) => (
          <label key={r} style={{ display: "block", fontSize: 14 }}>
            <input
              type="checkbox"
              checked={roles.includes(r)}
              onChange={(e) =>
                setRoles((cur) => (e.target.checked ? [...cur, r] : cur.filter((x) => x !== r)))
              }
            />{" "}
            {r}
          </label>
        ))}
      </fieldset>

      <label style={{ fontSize: 13 }}>
        Minimum clearance
        <input
          type="number" min={0} max={100} value={clearance}
          onChange={(e) => setClearance(Number(e.target.value))}
          style={{ marginLeft: 8, width: 80 }}
        />
      </label>

      <button onClick={submit} disabled={!canSubmit}>Upload and index</button>
      {!canSubmit && <small style={{ color: "#8b8a84" }}>Select a file and at least one role.</small>}
      {status && <small>{status}</small>}
    </div>
  );
}
