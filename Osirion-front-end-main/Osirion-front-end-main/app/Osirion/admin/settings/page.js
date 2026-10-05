"use client";

/**
 * Paramètres — section Configurer (thème clair). Général / Sécurité / Détection.
 * Persistance locale (siteName, sessionTimeout, passwordMinLength). Les réglages
 * système restent admin ; les opérateurs peuvent gérer les régimes horaires.
 */
import { useState, useEffect, useCallback } from "react";
import { Settings as Cog, Shield, Target, CheckCircle2, Save, RotateCcw, Cctv, Plug, Mail, Send, X } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Segmented, Banner } from "../_osirion/ui";
import WorkSchedules from "../_osirion/WorkSchedules";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const SETTINGS_STORAGE_KEY = "osirion-settings";
const PERSIST_KEYS = ["siteName", "sessionTimeout", "passwordMinLength"];


// ─────────────────────────────────────────────
// Saisie d'une LISTE d'adresses (destinataires d'alerte)
// ─────────────────────────────────────────────
// La valeur reste une chaîne séparée par des virgules — c'est ce que le backend
// stocke et ce que l'envoi découpe. Seule la SAISIE change : une adresse fautive
// n'échouait qu'au moment de l'envoi, avec une erreur SMTP illisible, et rien
// n'indiquait qu'on pouvait en mettre plusieurs.
const EMAIL_RE = /^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$/;

function RecipientsInput({ value, onChange, disabled }) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const list = (value || "").split(",").map((e) => e.trim()).filter(Boolean);

  const commit = (raw) => {
    // Virgule, point-virgule, espace et retour à la ligne séparent : un copier-
    // coller depuis un carnet d'adresses passe d'un coup.
    const morceaux = String(raw).split(/[,;\s]+/).map((m) => m.trim()).filter(Boolean);
    if (!morceaux.length) return true;
    const mauvais = morceaux.filter((m) => !EMAIL_RE.test(m));
    if (mauvais.length) {
      setError(`Adresse invalide : ${mauvais.join(", ")}`);
      return false;
    }
    const connus = new Set(list.map((e) => e.toLowerCase()));
    const ajouts = morceaux.filter((m) => !connus.has(m.toLowerCase()));
    if (ajouts.length) onChange([...list, ...ajouts].join(", "));
    setDraft("");
    setError("");
    return true;
  };

  const retirer = (adresse) => {
    onChange(list.filter((e) => e !== adresse).join(", "));
    setError("");
  };

  return (
    <div>
      <div className="w-full px-2 py-2 rounded-os border border-os-border bg-os-card flex flex-wrap items-center gap-1.5">
        {list.map((adresse) => (
          <span key={adresse}
            className="inline-flex items-center gap-1.5 rounded-os bg-os-card-2 border border-os-border-2 pl-2.5 pr-1 py-1 text-[13px] text-os-t1">
            {adresse}
            <button type="button" onClick={() => retirer(adresse)} disabled={disabled}
              aria-label={`Retirer ${adresse}`}
              className="h-5 w-5 grid place-items-center rounded text-os-t4 hover:text-os-red disabled:opacity-40">
              <X className="h-3.5 w-3.5" />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={draft}
          disabled={disabled}
          onChange={(e) => { setDraft(e.target.value); if (error) setError(""); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === "," || e.key === ";") { e.preventDefault(); commit(draft); }
            else if (e.key === "Backspace" && !draft && list.length) retirer(list[list.length - 1]);
          }}
          // Quitter le champ vaut validation : sans cela une adresse tapée puis
          // laissée telle quelle était perdue à l'enregistrement.
          onBlur={() => commit(draft)}
          onPaste={(e) => {
            const colle = e.clipboardData.getData("text");
            if (/[,;\s]/.test(colle)) { e.preventDefault(); commit(colle); }
          }}
          placeholder={list.length ? "Ajouter une adresse…" : "alerte@monsite.com"}
          className="flex-1 min-w-[200px] px-1.5 py-1 bg-transparent text-[14px] text-os-t1 outline-none"
        />
      </div>
      {error
        ? <p className="text-[12px] text-os-red mt-1.5">{error}</p>
        : <p className="text-[12px] text-os-t3 mt-1.5">
            {list.length === 0 ? "Aucun destinataire." : `${list.length} destinataire${list.length > 1 ? "s" : ""}.`}
            {" "}Entrée ou virgule pour ajouter.
          </p>}
    </div>
  );
}

export default function SettingsPage() {
  const user = useAuth();
  const isAdmin = user?.role === "admin";
  const isOperator = user?.role === "user";
  const [tab, setTab] = useState("general");
  const effectiveTab = isOperator ? "horaires" : tab;
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [localMsg, setLocalMsg] = useState(null);   // échec d'écriture/lecture du stockage local
  const [settings, setSettings] = useState({ siteName: "Qwiper Sentinel", sessionTimeout: 30, passwordMinLength: 8 });

  const change = (k, v) => { setSettings((p) => ({ ...p, [k]: v })); setDirty(true); };

  useEffect(() => {
    try {
      const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (!raw) return;
      const s = JSON.parse(raw);
      const sub = {};
      for (const k of PERSIST_KEYS) if (s[k] !== undefined) sub[k] = s[k];
      if (Object.keys(sub).length) setSettings((p) => ({ ...p, ...sub }));
      if (s.siteName) document.title = s.siteName;
    } catch { /* */ }
  }, []);

  const save = () => {
    try {
      const payload = {};
      for (const k of PERSIST_KEYS) payload[k] = settings[k];
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(payload));
      if (settings.siteName) document.title = settings.siteName;
    } catch {
      // L'écriture peut échouer : quota saturé, navigation privée, stockage
      // bloqué par le navigateur. On annonçait « Enregistré » quand même, et
      // le réglage disparaissait au rechargement sans que personne le sache.
      setLocalMsg({ ok: false, text: "Enregistrement impossible : le navigateur refuse le stockage local (navigation privée ou quota saturé)." });
      return;
    }
    setLocalMsg(null);
    setDirty(false); setSaved(true); setTimeout(() => setSaved(false), 2500);
  };
  const reset = () => {
    try {
      const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
      const s = raw ? JSON.parse(raw) : {};
      setSettings((p) => { const n = { ...p }; for (const k of PERSIST_KEYS) if (s[k] !== undefined) n[k] = s[k]; return n; });
    } catch {
      setLocalMsg({ ok: false, text: "Lecture du stockage local impossible : les valeurs affichées n'ont pas pu être rétablies." });
      return;
    }
    setLocalMsg(null);
    setDirty(false);
  };

  // ── HikCentral : config de connexion, persistée EN BASE (indépendante du localStorage) ──
  const [hik, setHik] = useState({ host: "", app_key: "", user_id: "", app_secret: "" });
  const [hikMeta, setHikMeta] = useState({ has_secret: false, source: null, configured: false, effective_host: null, loading: true });
  const [hikBusy, setHikBusy] = useState(null);   // "save" | "test" | null
  const [hikMsg, setHikMsg] = useState(null);     // { ok, text }

  const loadHik = useCallback(async () => {
    setHikMeta((m) => ({ ...m, loading: true }));
    try {
      const r = await fetchWithRefresh("/api/hikcentral/config");
      if (r?.ok) {
        const d = await r.json();
        setHik({ host: d.host || "", app_key: d.app_key || "", user_id: d.user_id || "", app_secret: "" });
        setHikMeta({ has_secret: !!d.has_secret, source: d.source, configured: !!d.configured, effective_host: d.effective_host, loading: false });
      } else setHikMeta((m) => ({ ...m, loading: false }));
    } catch {
      // Un échec de lecture laissait l'écran afficher « non configuré », ce qui
      // se confond avec une configuration réellement absente.
      setHikMeta((m) => ({ ...m, loading: false }));
      setHikMsg({ ok: false, text: "Configuration HikCentral illisible : vérifiez que le backend répond." });
    }
  }, []);
  useEffect(() => { loadHik(); }, [loadHik]);

  const hikField = (k, v) => { setHik((p) => ({ ...p, [k]: v })); setHikMsg(null); };
  const hikBody = () => {
    const b = { host: hik.host, app_key: hik.app_key, user_id: hik.user_id };
    if (hik.app_secret) b.app_secret = hik.app_secret;   // vide = conserver l'existant
    return b;
  };
  const saveHik = async () => {
    setHikBusy("save"); setHikMsg(null);
    try {
      const r = await fetchWithRefresh("/api/hikcentral/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(hikBody()) });
      const d = await r.json().catch(() => ({}));
      if (r?.ok) { setHikMsg({ ok: true, text: "Configuration enregistrée." }); await loadHik(); }
      else setHikMsg({ ok: false, text: d?.detail || d?.message || "Échec de l'enregistrement." });
    } catch { setHikMsg({ ok: false, text: "Erreur réseau." }); }
    finally { setHikBusy(null); }
  };
  const testHik = async () => {
    setHikBusy("test"); setHikMsg(null);
    try {
      const r = await fetchWithRefresh("/api/hikcentral/config/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(hikBody()) });
      const d = await r.json().catch(() => ({}));
      setHikMsg(r?.ok ? { ok: true, text: d?.message || "Connexion réussie." } : { ok: false, text: d?.detail || d?.message || "Échec de connexion." });
    } catch { setHikMsg({ ok: false, text: "Erreur réseau." }); }
    finally { setHikBusy(null); }
  };

  // ── Notifications (email SMTP + webhook), persistées EN BASE (comme HikCentral) ──
  const [notif, setNotif] = useState({ smtp_host: "", smtp_port: 587, smtp_user: "", smtp_password: "", smtp_from: "", smtp_use_tls: true, alert_email_to: "", alert_webhook_url: "", to: "" });
  const [notifMeta, setNotifMeta] = useState({ has_password: false, source: null, email_configured: false, webhook_configured: false, loading: true });
  const [notifBusy, setNotifBusy] = useState(null);   // "save" | "test" | null
  const [notifMsg, setNotifMsg] = useState(null);

  const loadNotif = useCallback(async () => {
    setNotifMeta((m) => ({ ...m, loading: true }));
    try {
      const r = await fetchWithRefresh("/api/notifications/config");
      if (r?.ok) {
        const d = await r.json();
        setNotif({
          smtp_host: d.smtp_host || "", smtp_port: d.smtp_port ?? 587, smtp_user: d.smtp_user || "",
          smtp_password: "", smtp_from: d.smtp_from || "", smtp_use_tls: d.smtp_use_tls ?? true,
          alert_email_to: d.alert_email_to || "", alert_webhook_url: d.alert_webhook_url || "", to: "",
        });
        setNotifMeta({ has_password: !!d.has_password, source: d.source, email_configured: !!d.email_configured, webhook_configured: !!d.webhook_configured, loading: false });
      } else setNotifMeta((m) => ({ ...m, loading: false }));
    } catch { setNotifMeta((m) => ({ ...m, loading: false })); }
  }, []);
  useEffect(() => { loadNotif(); }, [loadNotif]);

  const notifField = (k, v) => { setNotif((p) => ({ ...p, [k]: v })); setNotifMsg(null); };
  const notifBody = () => {
    const b = {
      smtp_host: notif.smtp_host, smtp_port: notif.smtp_port ? Number(notif.smtp_port) : null,
      smtp_user: notif.smtp_user, smtp_from: notif.smtp_from, smtp_use_tls: !!notif.smtp_use_tls,
      alert_email_to: notif.alert_email_to, alert_webhook_url: notif.alert_webhook_url,
    };
    if (notif.smtp_password) b.smtp_password = notif.smtp_password;   // vide = conserver
    return b;
  };
  const saveNotif = async () => {
    setNotifBusy("save"); setNotifMsg(null);
    try {
      const r = await fetchWithRefresh("/api/notifications/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(notifBody()) });
      const d = await r.json().catch(() => ({}));
      if (r?.ok) { setNotifMsg({ ok: true, text: "Configuration enregistrée." }); await loadNotif(); }
      else setNotifMsg({ ok: false, text: d?.detail || d?.message || "Échec de l'enregistrement." });
    } catch { setNotifMsg({ ok: false, text: "Erreur réseau." }); }
    finally { setNotifBusy(null); }
  };
  const testNotif = async () => {
    setNotifBusy("test"); setNotifMsg(null);
    try {
      const r = await fetchWithRefresh("/api/notifications/config/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...notifBody(), to: notif.to || undefined }) });
      const d = await r.json().catch(() => ({}));
      setNotifMsg(r?.ok ? { ok: true, text: d?.message || "Email de test envoyé." } : { ok: false, text: d?.detail || d?.message || "Échec de l'envoi." });
    } catch { setNotifMsg({ ok: false, text: "Erreur réseau." }); }
    finally { setNotifBusy(null); }
  };

  const inp = "w-full px-3.5 py-2.5 rounded-os border border-os-border bg-os-card text-[14px] text-os-t1 outline-none focus:border-os-t3";
  const lbl = "block text-[13px] font-semibold text-os-t1 mb-1.5";

  if (user && !isAdmin && !isOperator) {
    return <OsShell><div className="p-6"><Card className="p-10 text-center"><p className="text-[14px] text-os-t2">Accès réservé aux administrateurs.</p></Card></div></OsShell>;
  }

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Paramètres"
          subtitle="Configuration du système Qwiper Sentinel"
          actions={!isAdmin || ["hikcentral", "notifications", "horaires"].includes(effectiveTab) ? null : (
            <>
              {dirty && <span className="text-[12px] text-os-amber inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-os-amber os-anim-pulse" /> Non enregistré</span>}
              {saved && <span className="text-[12px] text-os-green inline-flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" /> Enregistré</span>}
              <button onClick={reset} className="px-3.5 py-2 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1 inline-flex items-center gap-2"><RotateCcw className="h-4 w-4" /> Réinitialiser</button>
              <button onClick={save} disabled={!dirty} className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover disabled:opacity-40 inline-flex items-center gap-2"><Save className="h-4 w-4" /> Enregistrer</button>
            </>
          )}
        />

        <div className="mb-5">
          <Segmented value={effectiveTab} onChange={setTab} options={isAdmin ? [{ value: "general", label: "Général" }, { value: "security", label: "Sécurité" }, { value: "detection", label: "Détection" }, { value: "horaires", label: "Régimes horaires" }, { value: "notifications", label: "Notifications" }, { value: "hikcentral", label: "HikCentral" }] : [{ value: "horaires", label: "Régimes horaires" }]} />
        </div>

        {effectiveTab === "general" && (
          <Card className="p-6 max-w-2xl">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Cog className="h-5 w-5" /></span>
              <div><h3 className="text-[15px] font-semibold text-os-t1">Paramètres généraux</h3></div>
            </div>
            <label className={lbl}>Nom du site</label>
            <input type="text" value={settings.siteName} onChange={(e) => change("siteName", e.target.value)} className={inp} />
            <p className="text-[12px] text-os-t3 mt-2">Affiché comme titre de l&apos;onglet du navigateur.</p>
            {localMsg && <Banner message={localMsg} className="mt-3" />}
          </Card>
        )}

        {effectiveTab === "security" && (
          <Card className="p-6 max-w-2xl">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Shield className="h-5 w-5" /></span>
              <div><h3 className="text-[15px] font-semibold text-os-t1">Sécurité & authentification</h3><p className="text-[13px] text-os-t3">Contrôle d&apos;accès</p></div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className={lbl}>Session (min)</label>
                <input type="number" min="0" max="120" value={settings.sessionTimeout} onChange={(e) => change("sessionTimeout", parseInt(e.target.value))} className={`${inp} os-num`} />
                <p className="text-[12px] text-os-t3 mt-2">Déconnexion auto après inactivité (à chaud, ≤ 15 s). <span className="text-os-t2">0 = désactivé</span> · une vidéo en lecture ne déconnecte pas.</p>
              </div>
              <div>
                <label className={lbl}>Mot de passe (min)</label>
                <input type="number" min="6" max="32" value={settings.passwordMinLength} onChange={(e) => change("passwordMinLength", parseInt(e.target.value))} className={`${inp} os-num`} />
                <p className="text-[12px] text-os-t3 mt-2">Longueur minimale à la création d&apos;un utilisateur.</p>
              </div>
            </div>
          </Card>
        )}

        {effectiveTab === "detection" && (
          <Card className="p-6 max-w-2xl">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Target className="h-5 w-5" /></span>
              <div><h3 className="text-[15px] font-semibold text-os-t1">Détection</h3><p className="text-[13px] text-os-t3">Moteur Core</p></div>
            </div>
            <p className="text-[13px] text-os-t3 rounded-os border border-os-border bg-os-card-2 p-4">
              La détection de personnes est toujours active sur les caméras. Les règles opérationnelles (attroupement, intrusion horaire…) se configurent dans « Règles & alertes ».
            </p>
          </Card>
        )}

        {/* Écriture : USER ou ADMIN, comme le backend (can_manage_cameras). */}
        {effectiveTab === "horaires" && <WorkSchedules canWrite={["admin", "user"].includes(user?.role)} />}

        {effectiveTab === "notifications" && (
          <Card className="p-6 max-w-2xl">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Mail className="h-5 w-5" /></span>
              <div>
                <h3 className="text-[15px] font-semibold text-os-t1">Notifications par email</h3>
                <p className="text-[13px] text-os-t3">Serveur SMTP pour l&apos;envoi des alertes</p>
              </div>
              <span className="ml-auto inline-flex items-center gap-1.5 text-[12px]">
                <span className="h-2 w-2 rounded-full" style={{ background: notifMeta.email_configured ? "var(--os-green)" : "var(--os-t4)" }} />
                <span className="text-os-t3">{notifMeta.email_configured ? "Configuré" : "Non configuré"}{notifMeta.source ? ` · ${notifMeta.source === "db" ? "base" : ".env"}` : ""}</span>
              </span>
            </div>

            {notifMeta.source === "env" && (
              <p className="mb-4 rounded-os border border-os-border bg-os-card-2 px-3.5 py-2.5 text-[12px] text-os-t3">
                ⓘ Aucune configuration saisie ici : le système utilise le repli <span className="os-num">.env</span>. Enregistrez ci-dessous pour piloter l&apos;envoi des emails depuis l&apos;interface.
              </p>
            )}

            <div className="space-y-4">
              <div>
                <label className={lbl}>Serveur SMTP</label>
                <div className="grid grid-cols-1 sm:grid-cols-[2fr_1fr] gap-4">
                  <input type="text" value={notif.smtp_host} onChange={(e) => notifField("smtp_host", e.target.value)} placeholder="smtp.gmail.com" className={inp} />
                  <input type="number" value={notif.smtp_port} onChange={(e) => notifField("smtp_port", e.target.value)} placeholder="587" className={`${inp} os-num`} />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className={lbl}>Utilisateur (login)</label>
                  <input type="text" value={notif.smtp_user} onChange={(e) => notifField("smtp_user", e.target.value)} placeholder="compte@gmail.com" className={inp} autoComplete="off" />
                </div>
                <div>
                  <label className={lbl}>Mot de passe</label>
                  <input type="password" value={notif.smtp_password} onChange={(e) => notifField("smtp_password", e.target.value)} autoComplete="new-password"
                    placeholder={notifMeta.has_password ? "•••••••• (laisser vide pour conserver)" : "Mot de passe d'application"} className={inp} />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className={lbl}>Expéditeur (From)</label>
                  <input type="text" value={notif.smtp_from} onChange={(e) => notifField("smtp_from", e.target.value)} placeholder="alertes@monsite.com" className={inp} />
                </div>
              </div>
              <div>
                <label className={lbl}>Destinataires</label>
                <RecipientsInput value={notif.alert_email_to} onChange={(v) => notifField("alert_email_to", v)} />
              </div>
              <label className="flex items-center gap-2.5 cursor-pointer select-none">
                <input type="checkbox" checked={!!notif.smtp_use_tls} onChange={(e) => notifField("smtp_use_tls", e.target.checked)} className="h-4 w-4 accent-[var(--os-cta)]" />
                <span className="text-[13px] text-os-t2">Chiffrement TLS (STARTTLS) — recommandé, port 587</span>
              </label>
              <div>
                <label className={lbl}>Webhook (facultatif)</label>
                <input type="text" value={notif.alert_webhook_url} onChange={(e) => notifField("alert_webhook_url", e.target.value)} placeholder="https://hooks.slack.com/…" className={inp} />
                <p className="text-[12px] text-os-t3 mt-1.5">POST JSON à chaque alerte notifiée (Slack / Teams / endpoint).</p>
              </div>
              <div className="pt-3 border-t border-os-border">
                <label className={lbl}>Email de test (facultatif)</label>
                <input type="text" value={notif.to} onChange={(e) => notifField("to", e.target.value)} placeholder="destinataire du test — sinon les destinataires ci-dessus" className={inp} />
              </div>
            </div>

            <p className="text-[12px] text-os-t3 mt-3">Mot de passe chiffré au repos, jamais réaffiché. Gmail : activez la validation en 2 étapes et utilisez un <b>mot de passe d&apos;application</b>. L&apos;envoi automatique s&apos;active <b>par règle</b> (Règles &amp; alertes).</p>
            {notifMsg && <Banner message={notifMsg} className="mt-3" />}

            <div className="mt-5 flex items-center gap-2">
              <button onClick={saveNotif} disabled={notifBusy != null}
                className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover disabled:opacity-50 inline-flex items-center gap-2">
                <Save className="h-4 w-4" /> {notifBusy === "save" ? "Enregistrement…" : "Enregistrer"}
              </button>
              <button onClick={testNotif} disabled={notifBusy != null}
                className="px-3.5 py-2 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1 disabled:opacity-50 inline-flex items-center gap-2">
                <Send className="h-4 w-4" /> {notifBusy === "test" ? "Envoi…" : "Envoyer un test"}
              </button>
            </div>
          </Card>
        )}

        {effectiveTab === "hikcentral" && (
          <Card className="p-6 max-w-2xl">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Cctv className="h-5 w-5" /></span>
              <div>
                <h3 className="text-[15px] font-semibold text-os-t1">Connexion HikCentral</h3>
                <p className="text-[13px] text-os-t3">Identifiants d&apos;accès à la passerelle OpenAPI</p>
              </div>
              <span className="ml-auto inline-flex items-center gap-1.5 text-[12px]">
                <span className="h-2 w-2 rounded-full" style={{ background: hikMeta.configured ? "var(--os-green)" : "var(--os-t4)" }} />
                <span className="text-os-t3">{hikMeta.configured ? "Configuré" : "Non configuré"}{hikMeta.source ? ` · ${hikMeta.source === "db" ? "base" : ".env"}` : ""}</span>
              </span>
            </div>

            {hikMeta.source === "env" && (
              <p className="mb-4 rounded-os border border-os-border bg-os-card-2 px-3.5 py-2.5 text-[12px] text-os-t3">
                ⓘ Aucune configuration saisie ici : le système utilise le repli <span className="os-num">.env</span>{hikMeta.effective_host ? ` (hôte : ${hikMeta.effective_host})` : ""}. Enregistrez ci-dessous pour piloter la connexion depuis l&apos;interface.
              </p>
            )}

            <div className="space-y-4">
              <div>
                <label className={lbl}>Hôte / Passerelle</label>
                <input type="text" value={hik.host} onChange={(e) => hikField("host", e.target.value)} placeholder="https://192.168.1.10:443" className={inp} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className={lbl}>App Key</label>
                  <input type="text" value={hik.app_key} onChange={(e) => hikField("app_key", e.target.value)} placeholder="Clé du partenaire" className={inp} />
                </div>
                <div>
                  <label className={lbl}>Linked User</label>
                  <input type="text" value={hik.user_id} onChange={(e) => hikField("user_id", e.target.value)} placeholder="ex. admin" className={inp} />
                </div>
              </div>
              <div>
                <label className={lbl}>App Secret</label>
                <input type="password" value={hik.app_secret} onChange={(e) => hikField("app_secret", e.target.value)} autoComplete="new-password"
                  placeholder={hikMeta.has_secret ? "•••••••• (laisser vide pour conserver)" : "Secret du partenaire"} className={inp} />
                <p className="text-[12px] text-os-t3 mt-1.5">Chiffré au repos, jamais réaffiché.</p>
              </div>
            </div>

            {hikMsg && <Banner message={hikMsg} className="mt-4" />}

            <div className="mt-5 flex items-center gap-2">
              <button onClick={saveHik} disabled={hikBusy != null}
                className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover disabled:opacity-50 inline-flex items-center gap-2">
                <Save className="h-4 w-4" /> {hikBusy === "save" ? "Enregistrement…" : "Enregistrer"}
              </button>
              <button onClick={testHik} disabled={hikBusy != null}
                className="px-3.5 py-2 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1 disabled:opacity-50 inline-flex items-center gap-2">
                <Plug className="h-4 w-4" /> {hikBusy === "test" ? "Test…" : "Tester la connexion"}
              </button>
            </div>
          </Card>
        )}
      </div>
    </OsShell>
  );
}
