import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
const ALLOWED = new Set(["acknowledge", "resolve", "notify"]);

// POST /api/alerts/:id/:action  (action ∈ acknowledge | resolve | notify)
// Le corps éventuel (ex. { channel } pour notify) est transmis tel quel.
export async function POST(req, { params }) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  const { id, action } = params;
  if (!ALLOWED.has(action)) {
    return NextResponse.json({ message: "Action inconnue." }, { status: 400 });
  }

  try {
    const body = await req.json().catch(() => ({}));
    const res = await fetch(`${BACKEND}/alerts/${id}/${action}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = typeof data?.detail === "string"
        ? data.detail
        : data?.detail?.message || "Erreur lors de l'action.";
      return NextResponse.json({ message: msg, detail: data?.detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
