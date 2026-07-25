import { NextRequest } from "next/server";

const API = process.env.API_URL ?? "http://localhost:8000";

// Forwards to FastAPI and passes Set-Cookie back untouched, so cookie flags
// (httpOnly, secure, sameSite) are decided in one place — the backend.
async function forward(req: NextRequest, path: string[], method: string) {
  const url = `${API}/${path.join("/")}${req.nextUrl.search}`;
  const body = method === "GET" || method === "DELETE" ? undefined : await req.text();

  const upstream = await fetch(url, {
    method,
    headers: {
      "content-type": req.headers.get("content-type") ?? "application/json",
      cookie: req.headers.get("cookie") ?? "",
    },
    body,
    redirect: "manual",
  });

  const headers = new Headers();
  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) headers.append("set-cookie", setCookie);
  headers.set("content-type", upstream.headers.get("content-type") ?? "application/json");

  return new Response(upstream.body, { status: upstream.status, headers });
}

export const GET = (r: NextRequest, ctx: { params: { path: string[] } }) =>
  forward(r, ctx.params.path, "GET");
export const POST = (r: NextRequest, ctx: { params: { path: string[] } }) =>
  forward(r, ctx.params.path, "POST");
export const DELETE = (r: NextRequest, ctx: { params: { path: string[] } }) =>
  forward(r, ctx.params.path, "DELETE");
