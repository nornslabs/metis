import { SignedInAs } from "@/components/auth/signed-in-as";
import { SignOutButton } from "@/components/auth/sign-out-button";

// Placeholder until the app shell (SHIP-224): proves the guard, the typed client and sign-out.
export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col items-start justify-center gap-3 p-6">
      <h1 className="text-xl font-semibold tracking-tight">What are you building?</h1>
      <SignedInAs />
      <SignOutButton />
    </main>
  );
}
