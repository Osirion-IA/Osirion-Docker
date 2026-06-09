import { NextResponse } from "next/server";

// Déconnexion : efface les cookies de session (access/refresh httpOnly +
// token_expires_at). Utilisé par la déconnexion automatique après inactivité
// (paramètre Sécurité « Session (min) »).
export async function POST() {
  const res = NextResponse.json({ success: true });
  for (const name of ["access_token", "refresh_token", "token_expires_at"]) {
    res.cookies.set(name, "", {
      path: "/",
      maxAge: 0,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
    });
  }
  return res;
}
