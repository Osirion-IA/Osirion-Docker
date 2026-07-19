"use client";

/**
 * Login Qwiper Sentinel — split : hero sombre (grille technique + logo hexagone) à gauche,
 * carte blanche de connexion à droite. 100 % anonyme : aucune mention de
 * reconnaissance faciale. Auto-contenu (aucune image externe → offline + CSP OK).
 */
import { useState } from "react";
import { OsMark } from "./Osirion/admin/_osirion/OsLogo";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!email || !password) { setError("Veuillez remplir tous les champs."); return; }
    setIsLoading(true);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setError(data?.message || "Identifiants incorrects.");
        setIsLoading(false);
        return;
      }
      window.location.href = "/Osirion/admin/cockpit";
    } catch {
      setError("Erreur de connexion au serveur.");
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" style={{ fontFamily: "var(--font-plex-sans), system-ui, sans-serif" }}>
      <div className="hidden lg:flex lg:flex-1 relative overflow-hidden bg-[#0d0f12] items-center justify-center">
        <div className="absolute inset-0 opacity-[0.5]" style={{
          backgroundImage: "linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }} />
        <div className="absolute left-[8%] right-[8%] top-[22%] h-px bg-gradient-to-r from-transparent via-[#e60027]/50 to-transparent" />
        <div className="absolute left-[14%] right-[26%] bottom-[24%] h-px bg-gradient-to-r from-transparent via-[#e60027]/30 to-transparent" />
        <div className="relative z-10 flex flex-col items-center">
          <OsMark size={112} />
          <p className="mt-6 text-white font-bold tracking-[0.18em] text-[30px] leading-none pl-[0.18em] whitespace-nowrap">QWIPER SENTINEL</p>
          <p className="mt-4 text-[13px] text-[#6b7480] tracking-[0.08em]"></p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-white p-6 lg:p-16">
        <div className="w-full max-w-[380px]">
          <div className="lg:hidden mb-8 flex items-center gap-2.5">
            <OsMark size={34} />
            <span className="font-bold tracking-[0.08em] text-[#1c2126] text-[16px] whitespace-nowrap">QWIPER SENTINEL</span>
          </div>

          <h1 className="text-[30px] font-bold text-[#1c2126] tracking-tight">Bienvenue</h1>
          <p className="text-[14px] text-[#8a929b] mt-1.5">Connectez-vous à votre poste de supervision.</p>

          <form onSubmit={handleSubmit} className="mt-9 space-y-5">
            {error && (
              <div className="px-3.5 py-3 rounded-os border border-[#e60027]/30 bg-[#e60027]/[0.06] text-[#c11] text-[13px]">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="ident" className="block text-[11px] font-semibold tracking-[0.08em] uppercase text-[#8a929b] mb-2">
                Identifiant
              </label>
              <input
                id="ident" type="text" autoComplete="username" required
                value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3.5 py-3 rounded-os border border-[#d7dbe0] bg-white text-[14px] text-[#1c2126] placeholder-[#b6bcc3] outline-none focus:border-[#1c2126] transition-colors"
                placeholder="prenom.nom"
              />
            </div>

            <div>
              <label htmlFor="pwd" className="block text-[11px] font-semibold tracking-[0.08em] uppercase text-[#8a929b] mb-2">
                Mot de passe
              </label>
              <input
                id="pwd" type="password" autoComplete="current-password" required
                value={password} onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3.5 py-3 rounded-os border border-[#d7dbe0] bg-white text-[14px] text-[#1c2126] placeholder-[#b6bcc3] outline-none focus:border-[#1c2126] transition-colors"
                placeholder="••••••••••••"
              />
            </div>

            <button
              type="submit" disabled={isLoading}
              className="w-full py-3 rounded-os bg-[#1c2126] text-white text-[14px] font-semibold hover:bg-[#2a3138] transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isLoading ? "Connexion…" : "Se connecter"}
            </button>
          </form>

          {/* <p className="text-[11px] text-[#b6bcc3] mt-10">
            © {new Date().getFullYear()} Qwiper Sentinel — Système on-premise · 100 % anonyme
          </p> */}
        </div>
      </div>
    </div>
  );
}
