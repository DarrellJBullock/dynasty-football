import type { Metadata } from "next";
import { Document } from "@/components/shell/Document";
import "../globals.css";

export const metadata: Metadata = {
  title: { default: "Dynasty Football: Next Gen", template: "%s · Dynasty Football" },
  description: "A league in Dynasty Football: Next Gen, shared read-only.",
  robots: { index: false, follow: false }, // (a shared link isn't for search engines)
};

/** A league's read-only public link: no account, no game shell. */
export default function ShareLayout({ children }: { children: React.ReactNode }) {
  return <Document>{children}</Document>;
}
