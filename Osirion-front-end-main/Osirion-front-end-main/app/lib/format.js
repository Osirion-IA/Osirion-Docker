// Formatage des durées et des dates — source UNIQUE.
//
// Treize formateurs coexistaient, un par écran : fmtWait et fmtDuration définis
// deux fois chacun, fmtWaitShort en troisième variante, plus fmtAge, fmtUptime,
// fmtDur, fmtDate, fmtTime, time, clock, ago, relTime. Mêmes calculs, cas
// limites divergents — c'est ainsi qu'un cumul hors-ligne s'affichait
// « 462552 min 38 s », faute de palier en jours dans l'une des copies.
//
// Le piège central est la lecture des horodatages : le backend renvoie de l'UTC
// SANS suffixe « Z ». `new Date("2026-10-05T14:30:00")` est alors interprété en
// heure LOCALE par le navigateur, ce qui décale tout l'affichage. parseUtc()
// règle ce point une fois pour toutes.

/** Date depuis un horodatage backend (UTC implicite), ou null si illisible. */
export function parseUtc(value) {
  if (!value) return null;
  // Horodatage numérique (epoch) : en secondes ou en millisecondes selon la
  // source. Le seuil 1e12 départage — l'écran Présence en reçoit des deux sortes.
  if (typeof value === "number") {
    const d = new Date(value < 1e12 ? value * 1000 : value);
    return isNaN(d.getTime()) ? null : d;
  }
  const s = String(value);
  // Un horodatage déjà zoné (Z, +01:00) est respecté ; sinon on force l'UTC.
  const iso = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(s) ? s : `${s}Z`;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

const nombre = (v) => (typeof v === "number" && isFinite(v) ? v : 0);

/**
 * Durée PRÉCISE, secondes toujours visibles — pour les attentes courtes.
 * Les secondes sont complétées à deux chiffres : dans un tableau en chasse
 * fixe (.os-num), « 2 min 03 s » s'aligne, « 2 min 3 s » saute.
 */
export function fmtWait(seconds, { empty = "0 s" } = {}) {
  if (seconds == null) return empty;
  const t = Math.max(0, Math.round(nombre(seconds)));
  if (t < 60) return `${t} s`;
  const m = Math.floor(t / 60);
  const s = t % 60;
  return `${m} min ${String(s).padStart(2, "0")} s`;
}

/**
 * Durée COMPACTE, deux unités au plus — pour les cumuls et les longues plages.
 * Le palier en jours est indispensable : un cumul de parc se compte en
 * centaines d'heures, illisibles autrement.
 */
export function fmtDuration(seconds, { empty = "0 s", compact = false } = {}) {
  if (seconds == null) return empty;
  const t = Math.max(0, Math.round(nombre(seconds)));
  if (t < 60) return `${t} s`;
  if (t < 3600) {
    const s = t % 60;
    return compact ? `${Math.floor(t / 60)} min` : `${Math.floor(t / 60)} min${s ? ` ${s} s` : ""}`;
  }
  if (t < 86400) {
    const m = Math.floor((t % 3600) / 60);
    return compact ? `${Math.floor(t / 3600)} h` : `${Math.floor(t / 3600)} h${m ? ` ${m} min` : ""}`;
  }
  const h = Math.floor((t % 86400) / 3600);
  return compact ? `${Math.floor(t / 86400)} j` : `${Math.floor(t / 86400)} j${h ? ` ${h} h` : ""}`;
}

/**
 * Temps écoulé rendu comme une DURÉE NUE (« 5 min », « 2 h 10 min »), sans
 * « il y a ». Sert là où la colonne mesure une ancienneté plutôt qu'elle ne
 * situe un instant — un poste vacant « depuis 12 min » se lit mieux ainsi.
 */
export function elapsed(value, { empty = "—", compact = false } = {}) {
  const d = parseUtc(value);
  if (!d) return empty;
  return fmtDuration(Math.max(0, (Date.now() - d.getTime()) / 1000), { compact });
}

/** Âge d'une mesure (fraîcheur). `—` quand la valeur est absente, pas « 0 s ». */
export const fmtAge = (seconds) =>
  seconds == null ? "—" : fmtWait(seconds);

/** Temps écoulé, en langage courant. */
export function relative(value, { empty = "—" } = {}) {
  const d = parseUtc(value);
  if (!d) return empty;
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 45) return "à l'instant";
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  // Au-delà d'un jour, « il y a 5 j » est moins utile que la date elle-même.
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
}

/** Date + heure courtes : « 05 oct. 14:32 ». */
export function dateTime(value, { seconds = false, empty = "—" } = {}) {
  const d = parseUtc(value);
  if (!d) return empty;
  return d.toLocaleString("fr-FR", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
  });
}

/** Heure seule : « 14:32:05 ». */
export function timeOnly(value, { seconds = true, empty = "—" } = {}) {
  const d = parseUtc(value);
  if (!d) return empty;
  return d.toLocaleTimeString("fr-FR", {
    hour: "2-digit", minute: "2-digit", ...(seconds ? { second: "2-digit" } : {}),
  });
}

/** Jour en toutes lettres : « vendredi 5 octobre ». */
export const dayLong = (date = new Date()) =>
  date.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
