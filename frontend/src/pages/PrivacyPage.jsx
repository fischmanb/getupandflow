import { Link } from "react-router-dom";

export function PrivacyPage() {
  return (
    <main className="auth-layout">
      <section className="auth-card legal-card">
        <p className="eyebrow">Get Up and Flow</p>
        <h1>Privacy Policy</h1>
        <p className="legal-effective">Effective July 24, 2026</p>
        <p className="subtle-copy">
          Coaching only works if you can be honest with your coach, and you can only be honest if you
          trust where your words go. So before the details, the promises: we never sell your data, we
          never use it for advertising, and session recordings and transcripts are used for one thing —
          delivering and improving your coaching.
        </p>

        <h2>1. What we collect</h2>
        <ul className="subtle-copy legal-list">
          <li>
            <strong>Account information.</strong> Your name, email address, and password (stored only as
            a secure hash — we can't read it).
          </li>
          <li>
            <strong>Onboarding preferences.</strong> Your timezone, preferred check-in windows, preferred
            contact method and contact number, and what you'd like help with.
          </li>
          <li>
            <strong>Payment details.</strong> Payments run through Stripe. We never see or store your
            card number — Stripe passes us only what we need to manage your subscription (your plan,
            its status, and your card's brand and last four digits).
          </li>
          <li>
            <strong>Session recordings and transcripts.</strong> Coaching sessions on Zoom are captured
            (audio/video) and transcribed, with the consent you give when you accept the Terms of
            Service at signup.
          </li>
          <li>
            <strong>Usage information.</strong> The plans, tasks, and events you create in the app, and
            basic records like logins — the things the product needs to function.
          </li>
        </ul>

        <h2>2. Why we collect it</h2>
        <p className="subtle-copy">
          To deliver your daily coaching; to give your coach continuity (they can review past
          transcripts instead of making you re-explain yourself); to improve the coaching experience; to
          run billing; and to keep the service secure. That's the whole list. We never sell your data
          and never use it for advertising.
        </p>

        <h2>3. How long we keep it</h2>
        <p className="subtle-copy">
          Session recordings are deleted from Zoom's cloud once the transcript has been ingested — we
          don't leave video sitting there. Transcripts are kept while you're a client so your coach has
          your history. Account and billing records are kept while your account is active, and
          afterwards only as long as tax and accounting rules require.
        </p>

        <h2>4. Who can see it</h2>
        <p className="subtle-copy">
          It depends on the kind of data, and for session content the answer is deliberately short.
          Session recordings and transcripts are hosted and transcribed via Zoom — that's what
          delivers the sessions. Beyond that hosting, your session content is never shared outside the
          company under any circumstances, with exactly two exceptions: (a) we believe there is a real
          risk of harm to you or to someone else, or (b) we are legally compelled to disclose it.
          Within the company, access to session content is limited to your own coach and GUAF's
          two-person leadership team, who review it for quality assurance — no one else. Every Get
          Up and Flow team member signs a confidentiality agreement binding them to client
          confidentiality, except if and when required by law. Your other data is narrower still: Stripe handles payment data, our email provider handles the emails we
          send you, and our hosting providers store account data — each only as needed to deliver the
          service, and none of them ever touch your session content. We never sell your data, and we
          never share it for advertising or marketing.
        </p>

        <h2>5. Your rights</h2>
        <p className="subtle-copy">
          You can ask for a copy of the data we hold about you, or ask us to delete it, by emailing{" "}
          <a href="mailto:hello@getupandflow.co">hello@getupandflow.co</a>. We'll confirm and act
          promptly. A small amount of billing data may need to stay for the retention periods the law
          requires; we'll tell you if that applies.
        </p>

        <h2>6. Changes to this policy</h2>
        <p className="subtle-copy">
          If we make meaningful changes, we'll let you know by email or an in-app notice before they
          take effect, and we'll update the effective date at the top of this page.
        </p>

        <h2>7. Contact</h2>
        <p className="subtle-copy">
          <a href="mailto:hello@getupandflow.co">hello@getupandflow.co</a> — a human reads it.
        </p>

        <p className="subtle-copy legal-links">
          <Link className="back-link" to="/terms">Terms of Service</Link>
          {" · "}
          <Link className="back-link" to="/login">Log in</Link>
          {" · "}
          <Link className="back-link" to="/signup">Sign up</Link>
        </p>
      </section>
    </main>
  );
}
