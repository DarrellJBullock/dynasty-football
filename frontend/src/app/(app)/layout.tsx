import type { Metadata } from "next";
import { Document } from "@/components/shell/Document";
import { Sidebar } from "@/components/shell/Sidebar";
import "../globals.css";

export const metadata: Metadata = {
  title: { default: "Dynasty Football: Next Gen", template: "%s · Dynasty Football" },
  description: "Build a football dynasty: manage your franchise, roster, and league.",
};

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Document>
      {/* For keyboard users: past the sidebar's links to the page. */}
      <a href="#main"
        className="sr-only z-50 rounded-md bg-gold px-3 py-2 text-sm font-semibold text-ink-950 focus:not-sr-only focus:fixed focus:left-3 focus:top-3">
        Skip to content
      </a>
      <div className="flex min-h-screen flex-col lg:flex-row">
        <Sidebar />
        <main id="main" tabIndex={-1}
          className="min-w-0 flex-1 px-4 pb-16 pt-6 outline-none sm:px-6 lg:px-10 lg:pt-8">
          {children}
        </main>
      </div>
    </Document>
  );
}
