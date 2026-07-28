import "./globals.css";

import { getPublicConfig } from "@/features/config/lib/dashboard-config";
import { AppShell } from "@/features/shell/components/app-shell";
import { Providers } from "@/features/shell/components/providers";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const config = await getPublicConfig();
  return {
    title: config.appName,
    description:
      "Playground dashboard for agent-orchestrator and game-service.",
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const config = getPublicConfig();

  return (
    <html className="h-full" suppressHydrationWarning lang="en">
      <body className="h-full overflow-hidden">
        <Providers>
          <AppShell appName={config.appName} bifrostUrl={config.bifrostUiUrl}>
            {children}
          </AppShell>
        </Providers>
      </body>
    </html>
  );
}
