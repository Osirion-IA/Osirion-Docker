import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// POST /api/hikcentral/config/test → teste la connexion (valeurs du formulaire ou
// config effective). Le backend relaie un 502 si HikCentral/les creds échouent.
export async function POST(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  let body = null;
  try { body = await req.json(); } catch { /* corps vide autorisé */ }
  try {
    const res = await fetch(`${BACKEND}/hikcentral/config/test`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
