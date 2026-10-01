import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// POST /api/hikcentral/sync → synchronise le catalogue (groupes + caméras).
export async function POST(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  try {
    const res = await fetch(`${BACKEND}/hikcentral/sync`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
