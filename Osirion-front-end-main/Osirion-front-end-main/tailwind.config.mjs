/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        // ── Palette Osirion (câblée sur les tokens CSS de globals.css) ──────
        os: {
          topbar: "var(--os-topbar)",
          sidebar: "var(--os-sidebar)",
          "sidebar-border": "var(--os-sidebar-border)",
          bg: "var(--os-bg)",
          card: "var(--os-card)",
          "card-2": "var(--os-card-2)",
          border: "var(--os-border)",
          "border-2": "var(--os-border-2)",
          t1: "var(--os-t1)",
          t2: "var(--os-t2)",
          t3: "var(--os-t3)",
          t4: "var(--os-t4)",
          cta: "var(--os-cta)",
          "cta-hover": "var(--os-cta-hover)",
          red: "var(--os-red)",
          green: "var(--os-green)",
          amber: "var(--os-amber)",
          blue: "var(--os-blue)",
        },
      },
      fontFamily: {
        // Rebrand : Plex Sans partout, Plex Mono pour tous les chiffres/métriques.
        sans: ["var(--font-plex-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        // Coins nets HikCentral : 3px (contrôles/cartes), 4px (grandes cartes).
        os: "3px",
        "os-lg": "4px",
      },
    },
  },
  plugins: [],
};
