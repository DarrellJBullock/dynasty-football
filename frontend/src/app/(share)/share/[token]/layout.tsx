import { Suspense } from "react";
import { ShareNav } from "@/components/share/ShareNav";

/** Every page of a public link: its nav (without the game's sidebar) above the page. */
export default function SharedLeagueLayout({ children, params }: LayoutProps<"/share/[token]">) {
  return (
    <div className="min-h-screen">
      {/* (The token is only known at request time.) */}
      <Suspense fallback={<div className="h-14 border-b border-white/5" />}>
        <Nav params={params} />
      </Suspense>
      <main id="main" className="px-4 pb-16 pt-6 sm:px-6 lg:px-10">{children}</main>
    </div>
  );
}

async function Nav({ params }: Pick<LayoutProps<"/share/[token]">, "params">) {
  const { token } = await params;
  return <ShareNav token={token} />;
}
