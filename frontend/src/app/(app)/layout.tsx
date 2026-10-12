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
      <div className="flex min-h-screen flex-col lg:flex-row">
        <Sidebar />
        <main className="min-w-0 flex-1 px-4 pb-16 pt-6 sm:px-6 lg:px-10 lg:pt-8">
          {children}
        </main>
      </div>
    </Document>
  );
}
