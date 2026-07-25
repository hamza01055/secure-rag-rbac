"use client";

import type { Citation } from "@/lib/api";

// Citations link to a document endpoint that re-checks authorization on click —
// never a signed URL minted at chat time, because a user's role can change
// between the answer and the click.
export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <ol style={{ fontSize: 13, color: "#575652", marginTop: 12, paddingLeft: 20 }}>
      {citations.map((c, i) => (
        <li key={c.chunk_id} style={{ marginBottom: 4 }}>
          <a href={`/api/proxy/documents/${c.document_id}`}>{c.filename}</a>
          {c.source_page ? ` · page ${c.source_page}` : ""}
          <span style={{ color: "#8b8a84" }}> · relevance {c.score.toFixed(2)}</span>
        </li>
      ))}
    </ol>
  );
}
