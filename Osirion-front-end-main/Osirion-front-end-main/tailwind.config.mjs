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
        // ── Palette Qwiper (câblée sur les tokens CSS de globals.css) ───────
        os: {
          primary: "var(--os-primary)",
          "primary-hover": "var(--os-primary-hover)",
          "on-primary": "var(--os-on-primary)",
          "brand-black": "var(--os-brand-black)",
          "brand-grey": "var(--os-brand-grey)",
          sidebar: "var(--os-sidebar)",
          "sidebar-border": "var(--os-sidebar-border)",
          "sidebar-t1": "var(--os-sidebar-t1)",
          "sidebar-t2": "var(--os-sidebar-t2)",
          "sidebar-t3": "var(--os-sidebar-t3)",
          "sidebar-hover": "var(--os-sidebar-hover)",
          "sidebar-active": "var(--os-sidebar-active)",
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
        // Marque Qwiper : Jost partout, Plex Mono pour les chiffres/métriques
        // (chasse fixe → compteurs alignés, cf. app/fonts.js).
        sans: ["var(--font-jost)", "system-ui", "sans-serif"],
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
