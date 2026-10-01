import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// GET /api/camera-status/<kind>?<query> → proxy vers backend /camera-status/<kind>.
// kind ∈ { stats, history }.
export async function GET(req, { params }) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  const { kind } = await params;
  const qs = req.nextUrl.search || "";
  try {
    const res = await fetch(`${BACKEND}/camera-status/${kind}${qs}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
