import { redirect } from "next/navigation";

/** The root has no page of its own. Signed in users land on the dashboard from /login. */
export default function Home() {
  redirect("/login");
}
