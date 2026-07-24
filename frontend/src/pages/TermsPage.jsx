import { Link } from "react-router-dom";

export function TermsPage() {
  return (
    <main className="auth-layout">
      <section className="auth-card legal-card">
        <p className="eyebrow">Get Up and Flow</p>
        <h1>Terms of Service</h1>
        <p className="legal-effective">Effective July 24, 2026</p>
        <p className="subtle-copy">
          These terms are the agreement between you and Get Up and Flow ("GUAF", "we", "us") when you
          create an account or use the service. We've written them in plain English on purpose — if
          anything is unclear, email us and a human will explain it.
        </p>

        <h2>1. What Get Up and Flow is</h2>
        <p className="subtle-copy">
          GUAF provides daily executive-function coaching for neurodivergent adults. A real human coach
          helps you plan your day, start the things you've been avoiding, and build momentum — over Zoom
          calls and text check-ins.
        </p>

        <h2>2. Coaching, not medical care</h2>
        <p className="subtle-copy">
          GUAF is a coaching service. It is not medical care, therapy, psychotherapy, counseling, or a
          clinical service of any kind, and using GUAF does not create a clinician–patient relationship.
          Our coaches are trained in executive-function support, but they are not licensed medical or
          mental-health providers, and nothing in a coaching session is medical advice. Coaching is not a
          substitute for diagnosis or treatment. If you are in crisis, contact a crisis line (in the US,
          call or text 988) or emergency services (911) — don't wait for a coaching session.
        </p>

        <h2>3. Session recording and transcription</h2>
        <p className="subtle-copy">
          Coaching sessions happen over Zoom. By accepting these terms, you consent to Get Up and Flow
          using Zoom audio/video capture and transcription of your coaching sessions to help improve the
          coaching experience. Recordings and transcripts help your coach remember exactly what you
          worked on together and help us make the coaching better. Section 4 covers how carefully we
          treat them.
        </p>

        <h2>4. Confidentiality</h2>
        <p className="subtle-copy">
          What you share in session stays confidential within Get Up and Flow. Session recordings
          and transcripts
          are strictly confidential. We never sell them, and we never share them or use them for any
          purpose beyond delivering and improving the coaching service. Sessions are hosted and
          transcribed via Zoom — that's what delivers the call and the transcript. Beyond that hosting,
          your session content is never shared outside the company under any circumstances, with
          exactly two exceptions: (a) we believe there is a real risk of harm to you or to someone
          else, or (b) we are legally compelled to disclose it. Within the company, access to session
          content is limited to your own coach and GUAF's two-person leadership team, who review it
          for quality assurance — no one else. Every Get Up and Flow team member signs a
          confidentiality agreement binding them to client confidentiality, except if and when
          required by law. The other providers we rely on — Stripe (payments), our email provider,
          and our hosting providers — handle only payment, email, and account data; they never
          touch your session content.
        </p>

        <h2>5. Plans, billing, and refunds</h2>
        <p className="subtle-copy">
          GUAF is a subscription, billed through Stripe. Plans and prices are shown at signup. If you're
          a new client and GUAF isn't working for you, you can get a full refund within 7 days of
          starting. After that you can cancel anytime through the billing portal in your account — your
          subscription runs to the end of the period you've paid for, and we don't refund partial
          periods.
        </p>

        <h2>6. Your coach</h2>
        <p className="subtle-copy">
          We'll assign your coach within 48 hours of signup. You work with the same coach every day, so
          they actually learn your patterns and what works for you — the whole idea is to build lasting
          rapport, and we train our coaches for exactly that. If your coach isn't the right fit, we'll
          accommodate a switch: you can change coaches once per year, pending availability.
        </p>

        <h2>7. Acceptable use</h2>
        <p className="subtle-copy">
          Treat your coach with the same decency they bring to you. Don't use GUAF to harass, threaten,
          or abuse anyone; don't try to break, probe, or overload our systems; don't misuse anyone
          else's data; and don't use the service for anything illegal. We can suspend or close accounts
          that do.
        </p>

        <h2>8. Your account</h2>
        <p className="subtle-copy">
          You must be at least 18 to use GUAF. Keep your login credentials to yourself and tell us right
          away if you think someone else has access to your account — you're responsible for activity
          that happens under your login.
        </p>

        <h2>9. Limitation of liability</h2>
        <p className="subtle-copy">
          We'll always do our honest best, but we provide the service "as is" and can't promise it will
          be uninterrupted or error-free. To the maximum extent the law allows, GUAF's total liability
          for any claim related to the service is limited to the amount you paid us in the three months
          before the claim arose, and we aren't liable for indirect, incidental, or consequential
          damages.
        </p>

        <h2>10. Changes to these terms</h2>
        <p className="subtle-copy">
          If we make meaningful changes to these terms, we'll let you know by email or an in-app notice
          before they take effect, and we'll update the effective date at the top of this page.
          Continuing to use GUAF after changes take effect means you accept the updated terms.
        </p>

        <h2>11. Governing law</h2>
        <p className="subtle-copy">
          These terms are governed by the laws of the State of New York, without regard to its
          conflict-of-law rules.
        </p>

        <h2>12. Questions</h2>
        <p className="subtle-copy">
          Email <a href="mailto:hello@getupandflow.co">hello@getupandflow.co</a> — a human reads it.
        </p>

        <p className="subtle-copy legal-links">
          <Link className="back-link" to="/privacy">Privacy Policy</Link>
          {" · "}
          <Link className="back-link" to="/login">Log in</Link>
          {" · "}
          <Link className="back-link" to="/signup">Sign up</Link>
        </p>
      </section>
    </main>
  );
}
