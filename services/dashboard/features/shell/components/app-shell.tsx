"use client";

import Image from "next/image";
import NextLink from "next/link";
import { usePathname } from "next/navigation";
import { PropsWithChildren } from "react";

import { useTheme } from "@/features/shell/components/providers";

function NavLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <NextLink
      href={href}
      className={[
        "rounded px-3 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-default-100 text-foreground"
          : "text-default-500 hover:bg-default-100/60 hover:text-foreground",
      ].join(" ")}
    >
      {children}
    </NextLink>
  );
}

export function AppShell({
  appName,
  children,
}: PropsWithChildren<{ appName: string }>) {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    // h-screen + flex-col so children can fill the remaining height
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-default-200/60 px-4">
        <div className="flex items-center gap-4">
          <NextLink
            href="/play"
            className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground/80 hover:text-foreground"
          >
            <Image src="/logo.webp" alt="Logo" width={20} height={20} />
            <span className="font-bold">{appName}</span>
          </NextLink>
          <nav className="flex items-center gap-1">
            <NavLink href="/play">Play</NavLink>
            <NavLink href="/games">Games</NavLink>
            <NavLink href="/history">History</NavLink>
            <NavLink href="/swagger">Swagger</NavLink>
          </nav>
        </div>

        {/* Theme toggle stays empty until the theme resolves to avoid hydration mismatch */}
        <button
          aria-label="Toggle colour theme"
          type="button"
          className="flex h-8 w-8 items-center justify-center rounded text-default-500 transition-colors hover:bg-default-100 hover:text-foreground"
          onClick={() => setTheme(isDark ? "light" : "dark")}
        >
          {resolvedTheme ? (isDark ? "☀" : "☾") : null}
        </button>
      </header>

      {/* ── Page content fills the rest ─────────────────────────── */}
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>
    </div>
  );
}
