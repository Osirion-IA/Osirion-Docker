import { NextResponse } from "next/server";

const ACCESS_TOKEN_TTL_MS = 30 * 60 * 1000; // 30 min, doit correspondre au backend
const IS_PROD = process.env.NODE_ENV === "production";

function setAuthCookies(res, accessToken, refreshToken) {
  res.cookies.set("access_token", accessToken, {
    httpOnly: true,
    path: "/",
    sameSite: "strict",
    secure: IS_PROD,
  });
  res.cookies.set("refresh_token", refreshToken, {
    httpOnly: true,
    path: "/",
    sameSite: "strict",
    secure: IS_PROD,
  });
  // Lisible par JS pour planifier le refresh proactif — ne contient que l'horodatage
  res.cookies.set("token_expires_at", String(Date.now() + ACCESS_TOKEN_TTL_MS), {
    httpOnly: false,
    path: "/",
    sameSite: "strict",
    secure: IS_PROD,
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
