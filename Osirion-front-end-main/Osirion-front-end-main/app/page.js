"use client";

import { useState } from "react";

import { Mail, Lock, ArrowRight } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!email || !password) {
      setError("Veuillez remplir tous les champs.");
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const data = await response.json();
        setError(data?.message || "Identifiants incorrects.");
        setIsLoading(false);
        return;
      }

      // Les tokens sont maintenant stockés côté serveur (httpOnly cookies)
      window.location.href = "/Osirion/admin";
    } catch (err) {
      setError("Erreur de connexion au serveur.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* GAUCHE : Formulaire */}
      <div className="flex-1 flex items-center justify-center bg-gray-950 p-6 lg:p-12 order-2 lg:order-1">
        <div className="w-full max-w-md">
          {/* Logo / Titre */}
          <div className="text-center mb-10">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-600 to-emerald-700 text-white text-3xl font-bold shadow-2xl shadow-emerald-900/30 mx-auto mb-4">
              OS
            </div>
            <h1 className="text-4xl font-bold text-white tracking-tight">
              Osirion
            </h1>
            <p className="text-emerald-400 mt-2 font-medium text-lg">
              Surveillance & Reconnaissance faciale en temps réel
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-7">
            {error && (
              <div className="p-4 bg-red-950/60 border border-red-800/50 text-red-300 rounded-xl text-sm">
                {error}
              </div>
            )}

            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-2">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-emerald-400/70" />
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-12 pr-5 py-3.5 bg-gray-900/70 border border-emerald-900/50 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 transition-all shadow-inner"
                  placeholder="admin@osirion.ai"
                />
              </div>
            </div>

            {/* Mot de passe */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label htmlFor="password" className="block text-sm font-medium text-gray-300">
                  Mot de passe
                </label>
                <a href="#" className="text-sm text-emerald-400 hover:text-emerald-300 hover:underline transition">
                  Mot de passe oublié ?
                </a>
              </div>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-emerald-400/70" />
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-12 pr-5 py-3.5 bg-gray-900/70 border border-emerald-900/50 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 transition-all shadow-inner"
                  placeholder="••••••••••••"
                />
              </div>
            </div>

            {/* Bouton principal */}
            <button
              type="submit"
              disabled={isLoading}
              className={`
                w-full flex items-center justify-center gap-3
                bg-gradient-to-r from-emerald-600 to-emerald-700
                text-white font-semibold py-3.5 rounded-xl
                shadow-lg shadow-emerald-900/40 hover:shadow-xl hover:from-emerald-500 hover:to-emerald-600
                focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:ring-offset-2 focus:ring-offset-gray-950
                transition-all duration-200
                disabled:opacity-60 disabled:cursor-not-allowed
              `}
            >
              {isLoading ? (
                <>Scan en cours...</>
              ) : (
                <>
                  Accéder à Osirion
                  <ArrowRight className="h-5 w-5" />
                </>
              )}
            </button>

            <p className="text-center text-sm text-gray-400 mt-8">
              Accès restreint — Système sécurisé Osirion
            </p>
          </form>

          <p className="text-center text-xs text-gray-500 mt-12">
            © {new Date().getFullYear()} Osirion — Tous droits réservés
          </p>
        </div>
      </div>

      {/* DROITE : Image thématique verte */}
      <div className="hidden lg:block lg:flex-1 relative bg-black overflow-hidden order-1 lg:order-2">
        <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-black/60 z-10" />

         <img
          src="https://images.unsplash.com/photo-1695902173528-0b15104c4554?q=80&w=1032&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"
          alt="Osirion - Reconnaissance faciale biométrique futuriste"
          className="absolute inset-0 w-full h-full object-cover object-center opacity-80"
        />

        {/* Overlay texte vert */}
        <div className="absolute inset-0 flex items-center justify-center text-center p-12 z-20">
          <div className="max-w-lg">
            <h2 className="text-5xl font-black text-emerald-400 drop-shadow-2xl mb-6 tracking-wider">
              OSIRION
            </h2>
            <p className="text-2xl text-white font-medium drop-shadow-lg mb-4">
              Identification biométrique instantanée
            </p>
            <p className="text-lg text-emerald-200/90 drop-shadow">
              Précision • Sécurité • Temps réel
            </p>
          </div>
        </div>

        {/* Effet scan subtil (optionnel, via CSS) */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-emerald-400/30 to-transparent animate-scan" />
        </div>
      </div>
    </div>
  );
}