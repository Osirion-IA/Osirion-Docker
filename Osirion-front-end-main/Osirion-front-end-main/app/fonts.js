// app/fonts.js
// Sora (marque Qwiper) + IBM Plex Mono, AUTO-HÉBERGÉES (.woff2 dans app/fonts/)
// via next/font/local — PAS next/font/google : le build Docker doit rester
// HORS-LIGNE (Google Fonts au build cassait la construction de l'image).
//
// Sora est VARIABLE : un seul fichier par sous-ensemble Unicode couvre toutes les
// graisses, d'où `weight: "100 800"` et deux fichiers (latin + latin-ext).
//
// Les CHIFFRES restent en IBM Plex Mono (classe .os-num) : Sora est à chasse
// proportionnelle, ses chiffres sauteraient en largeur dans les compteurs live.

import localFont from "next/font/local";

export const sora = localFont({
  src: [
    { path: "./fonts/sora-latin.woff2", weight: "100 800", style: "normal" },
    { path: "./fonts/sora-latin-ext.woff2", weight: "100 800", style: "normal" },
  ],
  variable: "--font-sora",
  display: "swap",
});

export const plexMono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-mono-600.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});
