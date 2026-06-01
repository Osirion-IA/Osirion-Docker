import { NextResponse } from "next/server";

const ACCESS_TOKEN_TTL_MS = 30 * 60 * 1000;
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
  res.cookies.set("token_expires_at", String(Date.now() + ACCESS_TOKEN_TTL_MS), {
    httpOnly: false,
    path: "/",
    sameSite: "strict",
    secure: IS_PROD,
  });
}

export async function POST(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const refreshToken = req.cookies.get("refresh_token")?.value;

    if (!refreshToken) {
      return NextResponse.json({ message: "Aucun refresh_token." }, { status: 401 });
    }

    const response = await fetch(`${backendUrl}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    const data = await response.json();
    if (!response.ok || !data.access_token || !data.refresh_token) {
      return NextResponse.json(
        { message: data?.message || "Impossible de rafraîchir le token." },
        { status: 401 }
      );
    }

    const res = NextResponse.json({ success: true });
    setAuthCookies(res, data.access_token, data.refresh_token);
    return res;
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
