import { redirect } from "next/navigation";

// La page d'accueil de l'admin est le Cockpit (section Surveiller).
export default function AdminIndex() {
  redirect("/Osirion/admin/cockpit");
}
