// app/fonts.js
// IBM Plex Sans + Mono AUTO-HÉBERGÉES (fichiers .woff2 vendorisés dans app/fonts/).
// On utilise next/font/local — PAS next/font/google — pour que le build Docker
// reste HORS-LIGNE (cf. note dans layout.js : Google Fonts cassait la build).
// Les variables CSS exposées (--font-plex-sans / --font-plex-mono) sont câblées
// dans tailwind.config (font-sans / font-mono) et globals.css.
import localFont from "next/font/local";

export const plexSans = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/ibm-plex-sans-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-plex-sans",
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
