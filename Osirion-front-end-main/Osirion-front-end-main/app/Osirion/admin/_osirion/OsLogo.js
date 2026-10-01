// Logo QWIPER — fichiers officiels de https://www.qwiper.com/brand, servis depuis
// public/brand/ (téléchargés dans le dépôt : aucun appel réseau à l'exécution).
//
// Deux variantes, à choisir selon le FOND :
//   • couleur (bleu + noir de marque) → fonds CLAIRS uniquement. Sur un fond
//     sombre, la moitié « noir de marque » du Q disparaîtrait.
//   • blanche → fonds sombres (sidebar, hero de connexion).
//
// `OsMark` = l'icône seule (le Q), `OsLogo` = le verrouillage produit complet
// (logotype Qwiper + nom du produit « SENTINEL »).
//
// Balises <img> natives, PAS next/image : l'optimiseur de Next 15 exige `sharp`,
// absent du projet, et son installation ferait dépendre le build du réseau — or
// l'image Docker doit se construire HORS-LIGNE (cf. app/fonts.js). Aucun gain à
// optimiser des fichiers déjà petits, affichés à taille fixe.

const MARK = {
  light: "/brand/qwiper-icon-cropped-hd.png", // Q couleur — pour fond clair
  dark: "/brand/qwiper-icon-white.png",       // Q blanc  — pour fond sombre
};
const WORDMARK = {
  light: "/brand/qwiper-logo-colors-hd.png",  // logotype couleur — pour fond clair
  dark: "/brand/qwiper-logo-white.png",       // logotype blanc  — pour fond sombre
};

// Rapports d'aspect des fichiers source (évite tout écrasement).
const MARK_RATIO = 1192 / 1098;   // ≈ 1.086
const WORD_RATIO = 3828 / 1209;   // ≈ 3.166

/** Icône Qwiper seule. `on` = fond sur lequel elle est posée ("dark" | "light"). */
export function OsMark({ size = 28, on = "dark", className = "" }) {
  return (
    <img
      src={MARK[on]}
      alt="Qwiper"
      width={Math.round(size * MARK_RATIO)}
      height={size}
      className={className}
      style={{ width: Math.round(size * MARK_RATIO), height: size }}
    />
  );
}

/**
 * Verrouillage produit : logotype Qwiper + « SENTINEL ».
 * `on`       : fond ("dark" par défaut — la sidebar est sombre dans les 2 thèmes).
 * `height`   : hauteur du logotype en px.
 * `product`  : afficher ou non le nom du produit sous le logotype.
 */
export default function OsLogo({ height = 22, on = "dark", product = true, className = "" }) {
  return (
    <span className={`inline-flex flex-col justify-center gap-[3px] ${className}`}>
      <img
        src={WORDMARK[on]}
        alt="Qwiper"
        width={Math.round(height * WORD_RATIO)}
        height={height}
        style={{ width: Math.round(height * WORD_RATIO), height }}
      />
      {product && (
        <span
          className="text-[9px] font-semibold uppercase tracking-[0.34em] leading-none"
          style={{ color: on === "dark" ? "var(--os-primary)" : "var(--os-brand-black)" }}
        >
          Sentinel
        </span>
      )}
    </span>
  );
}
