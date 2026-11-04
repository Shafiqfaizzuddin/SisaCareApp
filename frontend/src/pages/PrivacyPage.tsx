export function PrivacyPage() {
  return (
    <section className="section">
      <div className="container" style={{ maxWidth: 800 }}>
        <p className="eyebrow">SisaCare.AI</p>
        <h1>Privacy notice</h1>
        <p>Last updated 1 November 2026. SisaCare.AI is a student project for community waste reporting. It is not an official municipal service.</p>

        <h2>Information used by the app</h2>
        <p>Account registration and sign-in use your name, email address, and authentication details. Google sign-in supplies a verified email address and a stable Google account identifier. Waste reports may include your photo, description, selected incident location, and subsequent administrator status updates. The app also uses session cookies and basic server logs to operate and protect the service.</p>

        <h2>How it is used</h2>
        <p>Your report information is used to create and track a waste report and to let authorized administrators review it. Florence-2 and Ollama process analysis and draft text locally on the application host. AI output is a suggestion and may be corrected before submission.</p>

        <h2>Services involved</h2>
        <p>Supabase provides account authentication. Google provides sign-in and the optional incident map and place search. Cloudflare carries traffic to the application host. Email providers may deliver account and report status messages. These services process the information needed for their respective functions.</p>

        <h2>Access and retention</h2>
        <p>Signed-in users can view their own reports; authorized administrators can review and manage reports. Submitted reports and status history are retained for tracking and audit. A fixed deletion period has not been set for this project. Avoid including private information about other people in photos or descriptions.</p>

        <h2>Questions</h2>
        <p>For privacy questions, contact the project owner using the support address shown on the Google sign-in consent screen.</p>
      </div>
    </section>
  )
}
