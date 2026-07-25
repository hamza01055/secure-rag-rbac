"use client";

import { useEffect, useState } from "react";
import { api, type Principal } from "@/lib/api";
import { ChatWindow } from "@/components/ChatWindow";
import { RoleBadge } from "@/components/RoleBadge";

export default function ChatPage() {
  const [me, setMe] = useState<Principal | null>(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => (window.location.href = "/login"));
  }, []);

  return (
    <main>
      <header style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 32 }}>
        <h1 style={{ fontSize: 18, fontWeight: 500, margin: 0 }}>Ask your documents</h1>
        {me && <RoleBadge role={me.role} clearance={me.clearance} />}
        {me?.role === "Admin" && <a href="/admin" style={{ marginLeft: "auto" }}>Admin</a>}
      </header>
      <ChatWindow />
    </main>
  );
}
