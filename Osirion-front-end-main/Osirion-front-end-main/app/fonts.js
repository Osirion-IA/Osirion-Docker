// app/fonts.js
// Sora (police de marque Qwiper) + IBM Plex Mono, AUTO-HÉBERGÉES (.woff2 dans
// app/fonts/). On utilise next/font/local — PAS next/font/google — pour que le
// build Docker reste HORS-LIGNE (cf. note dans layout.js : Google Fonts cassait
// la build). Les variables exposées sont câblées dans tailwind.config + globals.css.
//
// Sora est une police VARIABLE : Google sert UN SEUL fichier par sous-ensemble
// Unicode, couvrant toutes les graisses. D'où `weight: "100 800"` et deux fichiers
// (latin + latin-ext) au lieu d'un fichier par graisse. L'axe s'arrête à 800 (et
// non 900 comme Jost) — l'interface ne dépasse pas 700 (font-bold), donc aucune
// graisse n'est synthétisée.
//
// Les CHIFFRES restent en IBM Plex Mono (classe .os-num) : Sora est une grotesque
// géométrique à chasse proportionnelle, ses chiffres sauteraient en largeur dans
// les compteurs rafraîchis en direct. Le mono garantit des colonnes stables.
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
