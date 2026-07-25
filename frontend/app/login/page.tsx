"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      await api.login(email, password);
      router.push("/chat");
    } catch {
      // One message for both cases. "No such user" tells an attacker which
      // emails exist.
      setError("Invalid email or password.");
    }
  }

  return (
    <main style={{ maxWidth: 340, margin: "12vh auto", display: "grid", gap: 12 }}>
      <h1 style={{ fontSize: 20, fontWeight: 500 }}>Sign in</h1>
      <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="password" type="password" value={password}
             onChange={(e) => setPassword(e.target.value)}
             onKeyDown={(e) => e.key === "Enter" && submit()} />
      <button onClick={submit}>Sign in</button>
      {error && <small style={{ color: "#a32d2d" }}>{error}</small>}
    </main>
  );
}
