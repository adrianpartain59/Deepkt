"use client";

import { useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import useAuthStore from "@/stores/authStore";

export default function AuthCallbackPage() {
    const searchParams = useSearchParams();
    const router = useRouter();

    useEffect(() => {
        const error = searchParams.get("error");
        if (error) {
            console.error("OAuth error:", error);
            router.replace("/");
            return;
        }

        const accessToken = searchParams.get("access_token");
        const refreshToken = searchParams.get("refresh_token");
        const userParam = searchParams.get("user");

        if (accessToken && refreshToken && userParam) {
            try {
                const user = JSON.parse(userParam);
                useAuthStore.getState().setTokensFromOAuth(accessToken, refreshToken, user);
            } catch (e) {
                console.error("Failed to parse OAuth user:", e);
            }
        }

        router.replace("/");
    }, [searchParams, router]);

    return (
        <div className="min-h-screen bg-black flex items-center justify-center">
            <p className="text-zinc-400 font-mono text-sm">Authenticating...</p>
        </div>
    );
}
