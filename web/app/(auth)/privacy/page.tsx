import type { Metadata } from "next";

import { LegalLink, LegalPage, LegalSection } from "@/components/legal/legal-page";

export const metadata: Metadata = { title: "Privacy · Metis" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="17 November 2026">
      <LegalSection heading="What we collect">
        <p>
          From Google sign-in: your email address, name and profile picture address. From you: the
          ideas, answers, workspaces and settings you enter, and the keys you add. Technical data
          such as request logs and the browser you sign in from is kept to run and secure the
          service.
        </p>
      </LegalSection>

      <LegalSection heading="Your keys">
        <p>
          LLM and search keys are encrypted before they are stored, are never shown again after you
          save them, and are decrypted only to make the calls you asked for.
        </p>
      </LegalSection>

      <LegalSection heading="Who receives your data">
        <p>
          Google, to sign you in. The LLM and search providers you configure, which receive the
          idea content needed to run an analysis; their own terms and privacy policies apply to
          that data. Metis does not sell your data or show ads.
        </p>
      </LegalSection>

      <LegalSection heading="Cookies and storage">
        <p>
          Metis sets one cookie, a session cookie that keeps you signed in. It cannot be read by
          page scripts, and only a hash of it is stored on the server. Your theme choice is kept in
          your browser. There are no tracking or advertising cookies.
        </p>
      </LegalSection>

      <LegalSection heading="Keeping and deleting data">
        <p>
          Your data is kept while your account exists. You can remove saved keys and end your
          sessions in Settings. There is no self-service account deletion yet; ask the operator of
          this deployment to delete your account and data.
        </p>
      </LegalSection>

      <LegalSection heading="Changes">
        <p>
          This policy may change as Metis does. The date above shows the latest version. See also
          the <LegalLink href="/terms">Terms of Use</LegalLink>.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
