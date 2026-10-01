import { NextResponse } from "next/server";

const ACCESS_TOKEN_TTL_MS = 30 * 60 * 1000; // 30 min, doit correspondre au backend
// Cookies "Secure" = envoyés uniquement en HTTPS. Pilotés par le mode :
//   • OSIRION_ENV=production  → Secure=true  (déploiement HTTPS)
//   • OSIRION_ENV=development → Secure=false (HTTP sur le LAN — sinon le navigateur
//     rejette les cookies et redirige au login sur tout poste sauf localhost).
// COOKIE_SECURE (true/false) force la valeur si besoin (ex. HTTP derrière un proxy TLS).
const IS_PROD = (process.env.OSIRION_ENV || "development").toLowerCase() === "production";
const COOKIE_SECURE =
  process.env.COOKIE_SECURE === "true" ? true :
  process.env.COOKIE_SECURE === "false" ? false :
  IS_PROD;

function setAuthCookies(res, accessToken, refreshToken) {
  res.cookies.set("access_token", accessToken, {
    httpOnly: true,
    path: "/",
    sameSite: "strict",
    secure: COOKIE_SECURE,
  });
  res.cookies.set("refresh_token", refreshToken, {
    httpOnly: true,
    path: "/",
    sameSite: "strict",
    secure: COOKIE_SECURE,
  });
  // Lisible par JS pour planifier le refresh proactif — ne contient que l'horodatage
  res.cookies.set("token_expires_at", String(Date.now() + ACCESS_TOKEN_TTL_MS), {
    httpOnly: false,
    path: "/",
    sameSite: "strict",
    secure: COOKIE_SECURE,
  });
}

export async function POST(req) {
  try {
    const { email, password } = await req.json();
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

    const response = await fetch(`${backendUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json();
    if (!response.ok || !data.access_token || !data.refresh_token) {
      return NextResponse.json(
        { message: data?.message || "Identifiants incorrects." },
        { status: 401 }
      );
    }

    const res = NextResponse.json({ success: true });
    setAuthCookies(res, data.access_token, data.refresh_token);
    return res;
  } catch {
    return NextResponse.json({ message: "Erreur de connexion au serveur." }, { status: 500 });
  }
}
