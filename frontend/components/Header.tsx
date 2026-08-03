"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export function Header({ backHref, backLabel }: { backHref?: string; backLabel?: string }) {
  const { user, logout } = useAuth();
  const router = useRouter();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <div className="app-header-left">
          <Link href="/shows" className="brand">
            <span className="brand-mark">SF</span>
            <span className="brand-name">SeatFlow</span>
          </Link>
          {backHref && (
            <Link href={backHref} className="back-link">
              &larr; {backLabel ?? "Back"}
            </Link>
          )}
        </div>
        {user && (
          <div className="app-header-right">
            <span className="user-email">{user.email}</span>
            <button className="btn btn-ghost btn-sm" onClick={handleLogout}>
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
