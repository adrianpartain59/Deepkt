"use client";

import dynamic from "next/dynamic";

// We MUST dynamically import the Canvas component with SSR disabled
// because Konva strictly requires the browser 'window' object to render.
const UniverseCanvas = dynamic(() => import("@/components/UniverseCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-screen bg-black text-[#e040fb] font-mono animate-pulse">
      IGNITING UNIVERSE...
    </div>
  ),
});

export default function Home() {
  return (
    <main className="w-full h-screen overflow-hidden bg-black relative">
      <UniverseCanvas />
    </main>
  );
}
