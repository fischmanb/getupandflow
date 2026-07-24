import { useState } from "react";

import { apiClient } from "../api/client";

/* Matching-phase goals: its own section on the members' room, editable while
   the match is being made. It resumes what the client already told us — their
   onboarding answer, or (when that is empty) the note they left on the
   marketing signup form (help_topics_seed, read-only until they save it). */
export function MatchingGoalsEditor({ prefs, onSaved }) {
  const [draft, setDraft] = useState(() => prefs?.help_topics || prefs?.help_topics_seed || "");
  const [saveState, setSaveState] = useState("idle");

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaveState("saving");
    try {
      const response = await apiClient.patch("/onboarding/", { help_topics: draft });
      onSaved(response.data || null);
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };

  return (
    <section className="home-goals-section">
      <p className="panel-label">Your goals</p>
      <form className="home-goals" onSubmit={handleSubmit}>
        <label className="home-goals-title" htmlFor="matching-goals-input">
          What I want help with
        </label>
        <p className="home-goals-explainer">
          This is what you shared when you signed up. Add to it any time — everything here shapes
          your match.
        </p>
        <textarea
          className="home-goals-input"
          id="matching-goals-input"
          placeholder="A few lines about what feels hard right now, or what you would like to be different — whatever comes to mind is a good place to start."
          rows={5}
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            if (saveState !== "idle") setSaveState("idle");
          }}
        />
        <div className="home-goals-actions">
          <button className="task-create-button" disabled={saveState === "saving"} type="submit">
            {saveState === "saving" ? "Saving…" : "Save"}
          </button>
          <span aria-live="polite" className="home-goals-status" role="status">
            {saveState === "saved" ? "Saved — this goes straight to your match." : null}
            {saveState === "error"
              ? "We could not save that just now. Your words are still here — try again in a moment."
              : null}
          </span>
        </div>
      </form>
    </section>
  );
}
