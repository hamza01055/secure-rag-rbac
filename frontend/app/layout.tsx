export const metadata = {
  title: "Secure RAG",
  description: "Retrieval-augmented generation with role-based access control",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, padding: 24, color: "#22221f" }}>
        {children}
      </body>
    </html>
  );
}
