"use client";

import React, { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import MenuPanel, { type PageTab } from "@/components/MenuPanel";
import CreatePage from "@/components/CreatePage";
import ProjectPage from "@/components/ProjectPage";
import AboutPage from "@/components/AboutPage";
import SettingsPage from "@/components/SettingsPage";
import AuthPage from "@/components/AuthPage";
import useAuthStore from "@/stores/authStore";

const UniverseCanvas = dynamic(() => import("@/components/UniverseCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-screen bg-black text-[#e040fb] font-mono animate-pulse">
      IGNITING UNIVERSE...
    </div>
  ),
});

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<PageTab>("explore");
  const [showSettings, setShowSettings] = useState(false);
  const [openProjectSlot, setOpenProjectSlot] = useState<number | null>(null);

  const { loadFromStorage, setTokensFromOAuth, user } = useAuthStore();

  // Initialize auth on mount
  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  // Listen for OAuth popup callbacks (Google/Apple)
  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (e.data?.type !== "auth-callback") return;
      if (e.data.error) {
        console.error("[auth] OAuth error:", e.data.error);
        return;
      }
      if (e.data.access_token && e.data.refresh_token && e.data.user) {
        setTokensFromOAuth(e.data.access_token, e.data.refresh_token, e.data.user);
        // Navigate away from auth page on successful login
        setActiveTab("explore");
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [setTokensFromOAuth]);

  // If user just logged in and was on auth page, go to explore
  useEffect(() => {
    if (user && activeTab === "auth") {
      setActiveTab("explore");
    }
  }, [user, activeTab]);

  return (
    <main className="w-full h-screen overflow-hidden bg-black relative">
      {/* Menu panel overlay */}
      <MenuPanel
        isOpen={menuOpen}
        onClose={() => setMenuOpen(false)}
        activeTab={showSettings ? "explore" : activeTab}
        onNavigate={(tab) => {
          setActiveTab(tab);
          setShowSettings(false);
          if (tab !== "create") setOpenProjectSlot(null);
        }}
        onSettings={() => setShowSettings(true)}
      />

      {/* Universe canvas is always mounted (preserves state) */}
      <UniverseCanvas onMenuOpen={() => setMenuOpen(true)} activeTab={activeTab} />

      {/* Page overlays */}
      {activeTab === "create" && openProjectSlot !== null && (
        <ProjectPage
          projectSlot={openProjectSlot}
          onBack={() => setOpenProjectSlot(null)}
        />
      )}
      {activeTab === "create" && openProjectSlot === null && (
        <CreatePage
          onMenuOpen={() => setMenuOpen(true)}
          onNavigateToAuth={() => setActiveTab("auth")}
          onOpenProject={(slot) => setOpenProjectSlot(slot)}
        />
      )}
      {activeTab === "about" && <AboutPage onMenuOpen={() => setMenuOpen(true)} />}
      {activeTab === "auth" && <AuthPage onMenuOpen={() => setMenuOpen(true)} />}
      {showSettings && <SettingsPage onMenuOpen={() => setMenuOpen(true)} />}
    </main>
  );
}
