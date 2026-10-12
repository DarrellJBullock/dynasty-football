import type { Metadata } from "next";
import { Document } from "@/components/shell/Document";
import "../globals.css";

export const metadata: Metadata = {
  title: { default: "Dynasty Football: Next Gen", template: "%s · Dynasty Football" },
  description: "Build a football dynasty: manage your franchise, roster, and league.",
};

/** Signing in and up: no game shell, just the form. */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <Document>
      <main className="flex min-h-screen items-center justify-center px-4 py-10">{children}</main>
    </Document>
  );
}
