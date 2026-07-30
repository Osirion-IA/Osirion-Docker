"use client";

/**
 * Paramètres — section Configurer (thème clair). Général / Sécurité / Détection.
 * Persistance locale (siteName, sessionTimeout, passwordMinLength). Admin only.
 */
import { useState, useEffect, useCallback } from "react";
import { Settings as Cog, Shield, Target, CheckCircle2, Save, RotateCcw, Cctv, Plug } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Segmented } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const SETTINGS_STORAGE_KEY = "osirion-settings";
const PERSIST_KEYS = ["siteName", "sessionTimeout", "passwordMinLength"];

export default function SettingsPage() {
  const user = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState("general");
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
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
    } catch { /* */ }
    setDirty(false); setSaved(true); setTimeout(() => setSaved(false), 2500);
  };
  const reset = () => {
    try {
      const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
      const s = raw ? JSON.parse(raw) : {};
      setSettings((p) => { const n = { ...p }; for (const k of PERSIST_KEYS) if (s[k] !== undefined) n[k] = s[k]; return n; });
    } catch { /* */ }
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
    } catch { setHikMeta((m) => ({ ...m, loading: false })); }
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

  const inp = "w-full px-3.5 py-2.5 rounded-os border border-os-border bg-os-card text-[14px] text-os-t1 outline-none focus:border-os-t3";
  const lbl = "block text-[13px] font-semibold text-os-t1 mb-1.5";

  if (user && !isAdmin) {
    return <OsShell><div className="p-6"><Card className="p-10 text-center"><p className="text-[14px] text-os-t2">Accès réservé aux administrateurs.</p></Card></div></OsShell>;
  }

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Paramètres"
          subtitle="Configuration du système Qwiper Sentinel"
          actions={tab === "hikcentral" ? null : (
            <>
              {dirty && <span className="text-[12px] text-os-amber inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-os-amber os-anim-pulse" /> Non enregistré</span>}
              {saved && <span className="text-[12px] text-os-green inline-flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" /> Enregistré</span>}
              <button onClick={reset} className="px-3.5 py-2 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1 inline-flex items-center gap-2"><RotateCcw className="h-4 w-4" /> Réinitialiser</button>
              <button onClick={save} disabled={!dirty} className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover disabled:opacity-40 inline-flex items-center gap-2"><Save className="h-4 w-4" /> Enregistrer</button>
            </>
          )}
        />

        <div className="mb-5">
          <Segmented value={tab} onChange={setTab} options={[{ value: "general", label: "Général" }, { value: "security", label: "Sécurité" }, { value: "detection", label: "Détection" }, { value: "hikcentral", label: "HikCentral" }]} />
        </div>

        {tab === "general" && (
          <Card className="p-6 max-w-2xl">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Cog className="h-5 w-5" /></span>
              <div><h3 className="text-[15px] font-semibold text-os-t1">Paramètres généraux</h3><p className="text-[13px] text-os-t3">Configuration de base</p></div>
            </div>
            <label className={lbl}>Nom du site</label>
            <input type="text" value={settings.siteName} onChange={(e) => change("siteName", e.target.value)} className={inp} />
            <p className="text-[12px] text-os-t3 mt-2">Affiché comme titre de l&apos;onglet du navigateur.</p>
          </Card>
        )}

        {tab === "security" && (
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

        {tab === "detection" && (
          <Card className="p-6 max-w-2xl">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Target className="h-5 w-5" /></span>
              <div><h3 className="text-[15px] font-semibold text-os-t1">Détection</h3><p className="text-[13px] text-os-t3">Moteur Core</p></div>
            </div>
            <p className="text-[13px] text-os-t3 rounded-os border border-os-border bg-os-card-2 p-4">
              La détection de personnes (anonyme) est toujours active sur les caméras. Les règles opérationnelles (attroupement, intrusion horaire…) se configurent dans « Règles & alertes ».
            </p>
          </Card>
        )}

        {tab === "hikcentral" && (
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

            {hikMsg && <p className={`mt-4 text-[13px] ${hikMsg.ok ? "text-os-green" : "text-os-red"}`}>{hikMsg.text}</p>}

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
