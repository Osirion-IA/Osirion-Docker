import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// POST /api/alerts/resolve-all  → résout en masse les alertes non résolues.
// Corps facultatif { status } transmis tel quel (voir backend /alerts/resolve-all).
export async function POST(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    const body = await req.json().catch(() => ({}));
    const res = await fetch(`${BACKEND}/alerts/resolve-all`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = typeof data?.detail === "string" ? data.detail : data?.detail?.message || "Erreur lors de l'action.";
      return NextResponse.json({ message: msg }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
