#!/usr/bin/env python3
# tools/analyze_metrics.py
"""
Dépouillement HORS-LIGNE du journal de mesure (measurements/metrics.jsonl) pour
renseigner les tableaux du chapitre 4 du mémoire (4.4 facial, 4.5 multi-caméras,
4.6 plaques).

Aucune dépendance externe (stdlib seule) → exécutable partout :

    python3 tools/analyze_metrics.py                       # fichier par défaut
    python3 tools/analyze_metrics.py measurements/metrics.jsonl
    python3 tools/analyze_metrics.py --scenario "4 cameras"   # filtrer un scénario

Le journal est découpé par SCÉNARIO (champ "scenario", posé par les marques
`/api/measure/mark`). Pour chaque scénario, on calcule :

  • Système (events system_sample)  → débit/caméra, latence facial+LPR, taux de
    succès du cache, occupation GPU                     → tableaux 4.4 et 4.5
  • Facial   (events recognition)   → rang-1, précision/rappel/F1, EER (balayage
    du seuil cosinus sur les décisions FAISS fraîches)  → tableau 4.4
  • Plaques  (events plate_read)    → CER + exactitude plaque entière (mono-image
    vs vote temporel), latence du pipeline LPR          → tableau 4.6
  • Recherche floue (events plate_lookup) → taux d'appariement                4.6

Convention de vérité terrain : `expected` "Inconnu"/"Unknown"/"" = imposteur
(non enrôlé) ; toute autre valeur = identité/plaque réellement présente.
"""
import sys
import os
import re
import json
import math
import argparse
from collections import defaultdict, Counter

UNKNOWN = {"", "inconnu", "unknown", "impostor", "imposteur", "none", "nobody"}


# ── Utilitaires statistiques (stdlib) ─────────────────────────────────────────
def percentile(values, p):
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def fmt(x, nd=1):
    return "—" if x is None else f"{x:.{nd}f}"


def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def norm_plate(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def is_unknown(label):
    return (label or "").strip().lower() in UNKNOWN


def parse_pct(s):
    """'12.3%' -> 12.3 ; nombre -> tel quel ; sinon None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"[-+]?\d*\.?\d+", str(s))
    return float(m.group()) if m else None


# ── Chargement ────────────────────────────────────────────────────────────────
def load(path):
    recs = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  (ligne {ln} ignorée : JSON invalide)", file=sys.stderr)
    return recs


# ── Système (tableaux 4.4 / 4.5) ──────────────────────────────────────────────
def analyze_system(samples):
    if not samples:
        return None
    n_cams = Counter()
    proc_fps_total, cap_fps_total = [], []
    face_p50, face_p95, lpr_p50, lpr_p95 = [], [], [], []
    hit_rates, gpu_util, gpu_mem_mb, gpu_mem_pct = [], [], [], []
    per_cam_fps = defaultdict(list)

    for s in samples:
        cams = s.get("cameras", []) or []
        n_cams[s.get("n_cameras", len(cams))] += 1
        tot_proc = 0.0
        for c in cams:
            pf = c.get("processed_fps")
            if pf is not None:
                tot_proc += pf
                per_cam_fps[c.get("id")].append(pf)
            if c.get("capture_fps") is not None:
                cap_fps_total.append(c["capture_fps"])
            fm = (c.get("face_ms") or {})
            if fm.get("p50") is not None:
                face_p50.append(fm["p50"])
            if fm.get("p95") is not None:
                face_p95.append(fm["p95"])
            lm = (c.get("lpr_ms") or {})
            if lm.get("p50") is not None:
                lpr_p50.append(lm["p50"])
            if lm.get("p95") is not None:
                lpr_p95.append(lm["p95"])
        if cams:
            proc_fps_total.append(tot_proc)
        hr = parse_pct((s.get("cache") or {}).get("cache_hit_rate"))
        if hr is not None:
            hit_rates.append(hr)
        gpus = (s.get("gpu") or {}).get("gpus") or []
        if gpus:
            g = gpus[0]
            if g.get("utilization_percent") is not None:
                gpu_util.append(g["utilization_percent"])
            if g.get("memory_used_mb") is not None:
                gpu_mem_mb.append(g["memory_used_mb"])
            if g.get("memory_percent") is not None:
                gpu_mem_pct.append(g["memory_percent"])

    cache = (samples[-1].get("cache") or {})
    return {
        "n_samples": len(samples),
        "n_cameras_mode": n_cams.most_common(1)[0][0] if n_cams else None,
        "proc_fps_total_mean": mean(proc_fps_total),
        "proc_fps_per_cam_mean": mean([mean(v) for v in per_cam_fps.values()]) if per_cam_fps else None,
        "capture_fps_mean": mean(cap_fps_total),
        "face_ms_p50": mean(face_p50), "face_ms_p95": mean(face_p95),
        "lpr_ms_p50": mean(lpr_p50), "lpr_ms_p95": mean(lpr_p95),
        "cache_hit_rate_mean": mean(hit_rates),
        "cache_hit_rate_last": parse_pct(cache.get("cache_hit_rate")),
        "cache_hits": cache.get("cache_hits"), "cache_misses": cache.get("cache_misses"),
        "gpu_util_mean": mean(gpu_util), "gpu_util_max": max(gpu_util) if gpu_util else None,
        "gpu_mem_mb_mean": mean(gpu_mem_mb), "gpu_mem_pct_mean": mean(gpu_mem_pct),
        "per_cam_fps": {k: mean(v) for k, v in per_cam_fps.items()},
    }


# ── Facial (tableau 4.4) ──────────────────────────────────────────────────────
def analyze_face(recs):
    labeled = [r for r in recs if "expected" in r and r.get("expected") is not None]
    if not labeled:
        return None
    fresh = [r for r in labeled if not r.get("from_cache")]   # décisions FAISS fraîches

    # Rang-1 : top-1 == identité réelle, sur probes de personnes KNOWN.
    known = [r for r in fresh if not is_unknown(r.get("expected"))]
    rank1 = (sum(1 for r in known
                 if (r.get("candidate") or "").strip().lower()
                 == (r.get("expected") or "").strip().lower()) / len(known)) if known else None

    # Précision / rappel / F1 de la décision accepter/rejeter (FAISS frais).
    tp = fp = fn = tn = 0
    for r in fresh:
        acc = bool(r.get("accepted"))
        exp = r.get("expected"); cand = r.get("candidate")
        correct_id = (cand or "").strip().lower() == (exp or "").strip().lower()
        if is_unknown(exp):
            if acc:
                fp += 1          # imposteur accepté → fausse acceptation
            else:
                tn += 1
        else:
            if acc and correct_id:
                tp += 1          # bon match accepté
            elif acc and not correct_id:
                fp += 1          # mauvaise identité acceptée
            else:
                fn += 1          # personne connue rejetée
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)

    # EER : balayage du seuil cosinus. Genuine = top-1 correct ; imposteur = top-1
    # incorrect (y compris probes d'imposteurs).
    genuine = [r["cosine_score"] for r in fresh
               if not is_unknown(r.get("expected"))
               and (r.get("candidate") or "").strip().lower() == (r.get("expected") or "").strip().lower()
               and r.get("cosine_score") is not None]
    impostor = [r["cosine_score"] for r in fresh
                if (is_unknown(r.get("expected"))
                    or (r.get("candidate") or "").strip().lower() != (r.get("expected") or "").strip().lower())
                and r.get("cosine_score") is not None]
    eer = eer_thr = None
    if genuine and impostor:
        thrs = sorted(set(genuine + impostor))
        best = None
        for t in thrs:
            far = sum(1 for s in impostor if s >= t) / len(impostor)
            frr = sum(1 for s in genuine if s < t) / len(genuine)
            d = abs(far - frr)
            if best is None or d < best[0]:
                best = (d, (far + frr) / 2.0, t)
        eer, eer_thr = best[1], best[2]

    return {
        "n_decisions": len(labeled), "n_fresh": len(fresh),
        "rank1": rank1, "precision": precision, "recall": recall, "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "eer": eer, "eer_threshold": eer_thr,
        "n_genuine": len(genuine), "n_impostor": len(impostor),
    }


# ── Plaques (tableau 4.6) ─────────────────────────────────────────────────────
def analyze_plate(reads, lookups):
    labeled = [r for r in reads if r.get("expected")]
    out = {"n_reads": len(reads), "n_labeled": len(labeled)}
    if labeled:
        def cer(field):
            num = den = 0
            for r in labeled:
                exp = norm_plate(r.get("expected"))
                got = norm_plate(r.get(field))
                if not exp:
                    continue
                num += levenshtein(got, exp)
                den += len(exp)
            return (num / den) if den else None

        def exact(field):
            ok = sum(1 for r in labeled
                     if norm_plate(r.get(field)) == norm_plate(r.get("expected")))
            return ok / len(labeled)

        cer_mono, cer_voted = cer("mono"), cer("voted")
        out.update({
            "cer_mono": cer_mono, "cer_voted": cer_voted,
            "char_acc_mono": (1 - cer_mono) if cer_mono is not None else None,
            "char_acc_voted": (1 - cer_voted) if cer_voted is not None else None,
            "exact_mono": exact("mono"), "exact_voted": exact("voted"),
            "lat_mono_ms": mean([(r.get("detect_ms") or 0) + (r.get("first_ocr_ms") or 0)
                                 for r in labeled if r.get("first_ocr_ms") is not None]),
            "lat_voted_ms": mean([r.get("time_to_finalize_ms") for r in labeled
                                  if r.get("time_to_finalize_ms") is not None]),
            "non_empty_rate": sum(1 for r in labeled if norm_plate(r.get("voted"))) / len(labeled),
        })
    if lookups:
        out["n_lookups"] = len(lookups)
        out["lookup_match_rate"] = sum(1 for l in lookups if l.get("matched")) / len(lookups)
    return out


# ── Rendu ─────────────────────────────────────────────────────────────────────
def print_scenario(name, recs):
    by = defaultdict(list)
    for r in recs:
        by[r.get("event")].append(r)

    print("\n" + "=" * 78)
    print(f"SCÉNARIO : {name}   ({len(recs)} événements)")
    print("=" * 78)

    sysm = analyze_system(by.get("system_sample", []))
    if sysm:
        print("\n— Système (tableaux 4.4 / 4.5) —")
        print(f"  Caméras actives (mode)        : {sysm['n_cameras_mode']}   "
              f"({sysm['n_samples']} échantillons)")
        print(f"  Débit total traité (FPS)      : {fmt(sysm['proc_fps_total_mean'])}")
        print(f"  Débit par caméra (FPS)        : {fmt(sysm['proc_fps_per_cam_mean'])}   "
              f"(capture ~{fmt(sysm['capture_fps_mean'])})")
        print(f"  Latence facial ms/frame       : p50={fmt(sysm['face_ms_p50'])}  "
              f"p95={fmt(sysm['face_ms_p95'])}")
        print(f"  Latence LPR (synchro) ms/frame: p50={fmt(sysm['lpr_ms_p50'])}  "
              f"p95={fmt(sysm['lpr_ms_p95'])}")
        print(f"  Taux succès cache             : {fmt(sysm['cache_hit_rate_last'])}%   "
              f"(moy {fmt(sysm['cache_hit_rate_mean'])}%, "
              f"hits={sysm['cache_hits']} miss={sysm['cache_misses']})")
        print(f"  GPU util / mémoire            : {fmt(sysm['gpu_util_mean'])}% moy "
              f"({fmt(sysm['gpu_util_max'])}% max) / {fmt(sysm['gpu_mem_mb_mean'])} Mo "
              f"({fmt(sysm['gpu_mem_pct_mean'])}%)")
        if sysm["per_cam_fps"]:
            pc = "  ".join(f"cam{k}={fmt(v)}" for k, v in sorted(sysm["per_cam_fps"].items()))
            print(f"  FPS par caméra                : {pc}")

    fa = analyze_face(by.get("recognition", []))
    if fa:
        print("\n— Facial (tableau 4.4, colonne GPU) —")
        print(f"  Décisions (dont FAISS frais)  : {fa['n_decisions']} ({fa['n_fresh']})")
        print(f"  Taux identification rang-1    : "
              f"{fmt((fa['rank1'] or 0) * 100) if fa['rank1'] is not None else '—'}%")
        print(f"  Précision / Rappel / F1       : {fmt((fa['precision'] or 0)*100) if fa['precision'] is not None else '—'}% / "
              f"{fmt((fa['recall'] or 0)*100) if fa['recall'] is not None else '—'}% / "
              f"{fmt((fa['f1'] or 0)*100) if fa['f1'] is not None else '—'}%")
        print(f"    (TP={fa['tp']} FP={fa['fp']} FN={fa['fn']} TN={fa['tn']})")
        if fa["eer"] is not None:
            print(f"  EER (seuil cosinus)           : {fmt(fa['eer']*100)}%  "
                  f"@ seuil={fmt(fa['eer_threshold'],3)}   "
                  f"(genuine={fa['n_genuine']}, impostor={fa['n_impostor']})")
        else:
            print(f"  EER                           : — (besoin de probes genuine ET "
                  f"imposteur ; genuine={fa['n_genuine']}, impostor={fa['n_impostor']})")

    pl = analyze_plate(by.get("plate_read", []), by.get("plate_lookup", []))
    if pl.get("n_reads"):
        print("\n— Plaques (tableau 4.6 : mono-image vs vote temporel) —")
        print(f"  Lectures finalisées (étiquetées): {pl['n_reads']} ({pl['n_labeled']})")
        if pl.get("n_labeled"):
            print(f"  Exactitude OCR/caractère (1-CER): mono={fmt((pl['char_acc_mono'] or 0)*100) if pl['char_acc_mono'] is not None else '—'}%   "
                  f"voté={fmt((pl['char_acc_voted'] or 0)*100) if pl['char_acc_voted'] is not None else '—'}%")
            print(f"  Exactitude plaque entière       : mono={fmt(pl['exact_mono']*100)}%   "
                  f"voté={fmt(pl['exact_voted']*100)}%")
            print(f"  Latence pipeline LPR (ms)       : mono={fmt(pl['lat_mono_ms'])}   "
                  f"voté(→finalisation)={fmt(pl['lat_voted_ms'])}")
            print(f"  Taux de lecture non vide        : {fmt(pl['non_empty_rate']*100)}%")
        if pl.get("n_lookups"):
            print(f"  Recherche floue : appariées     : {fmt(pl['lookup_match_rate']*100)}% "
                  f"sur {pl['n_lookups']} requêtes")


def main():
    ap = argparse.ArgumentParser(description="Dépouille metrics.jsonl → tableaux ch.4")
    ap.add_argument("path", nargs="?", default="measurements/metrics.jsonl")
    ap.add_argument("--scenario", help="ne traiter que ce scénario (sous-chaîne)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f"Fichier introuvable : {args.path}", file=sys.stderr)
        sys.exit(1)

    recs = load(args.path)
    print(f"Chargé : {len(recs)} événements depuis {args.path}")
    ev = Counter(r.get("event") for r in recs)
    print("Répartition : " + ", ".join(f"{k}={v}" for k, v in ev.most_common()))

    scenarios = defaultdict(list)
    for r in recs:
        scenarios[r.get("scenario", "(sans scénario)")].append(r)

    for name, rs in scenarios.items():
        if args.scenario and args.scenario.lower() not in str(name).lower():
            continue
        print_scenario(name, rs)

    print("\n" + "=" * 78)
    print("Rappel méthodo : EER/F1 calculés sur les décisions FAISS FRAÎCHES ; "
          "rang-1 sur probes\nde personnes connues. Petit N = échelle prototype "
          "(à présenter comme tel).")
    print("=" * 78)


if __name__ == "__main__":
    main()
