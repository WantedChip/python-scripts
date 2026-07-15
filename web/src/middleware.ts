import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const BOOTED_COOKIE = "pyscripts_booted";

/**
 * On the very first visit (no boot cookie), redirect `/` → `/boot`.
 * After the user types `home` from the terminal and lands on `/`,
 * the cookie will already be set (set by /boot page's client), so
 * subsequent hard-refreshes skip the boot screen.
 *
 * The cookie is session-scoped (no `maxAge`) — closing the browser
 * resets it so the boot plays again on a fresh session.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Only intercept the exact root path
  if (pathname !== "/") return NextResponse.next();

  // If the session cookie exists, let them through
  const booted = request.cookies.get(BOOTED_COOKIE);
  if (booted?.value === "1") return NextResponse.next();

  // First visit — send to boot
  const bootUrl = request.nextUrl.clone();
  bootUrl.pathname = "/boot";
  return NextResponse.redirect(bootUrl);
}

export const config = {
  // Only run middleware on `/` — never on API routes, static files, etc.
  matcher: ["/"],
};
