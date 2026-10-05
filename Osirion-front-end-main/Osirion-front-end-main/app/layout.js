import "./globals.css";
import { ThemeProvider } from "./ThemeProvider";
import { sora, plexMono } from "./fonts";

// Polices Sora (marque Qwiper) + IBM Plex Mono (chiffres) AUTO-HÉBERGÉES via
// next/font/local (fichiers .woff2 dans app/fonts/). On n'utilise PAS
// next/font/google : Google Fonts imposait un téléchargement réseau AU BUILD
// (`npm run build`) qui cassait la construction de l'image dès que
// fonts.googleapis.com était injoignable. Le local reste hors-ligne.

export const metadata = {
  title: "Qwiper Sentinel — Supervision vidéo opérationnelle",
  description: "Plateforme d'intelligence opérationnelle vidéo.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="fr" suppressHydrationWarning className={`${sora.variable} ${plexMono.variable}`}>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const theme = localStorage.getItem('osirion-theme') || 'system';
                const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
                if (isDark) {
                  document.documentElement.classList.add('dark');
                  document.documentElement.style.colorScheme = 'dark';
                } else {
                  document.documentElement.classList.remove('dark');
                  document.documentElement.style.colorScheme = 'light';
                }
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body className="antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
