"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { token, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(token ? "/shows" : "/login");
  }, [loading, token, router]);

  return (
    <div className="full-screen-center">
      <div className="spinner" />
    </div>
  );
}
