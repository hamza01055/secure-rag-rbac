import { NextRequest, NextResponse } from "next/server";

// Convenience, not security. The server enforces authorization on every
// endpoint regardless of what this lets through — assume every route is called
// directly with curl, because eventually it will be.
export function middleware(req: NextRequest) {
  const token = req.cookies.get("access_token");
  const isProtected = /^\/(chat|admin)/.test(req.nextUrl.pathname);
  if (isProtected && !token) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/chat/:path*", "/admin/:path*"] };
