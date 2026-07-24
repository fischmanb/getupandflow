/**
 * Matching-phase goals editing contract (home polish round 2):
 *   - while a client-self is unassigned, Home carries a "What I want help with"
 *     section of its own (outside the matching card) that PATCHes the existing
 *     onboarding record and explains that it resumes what they already shared
 *   - an empty goals answer is seeded (read-only until saved) from the
 *     marketing lead message the backend exposes as help_topics_seed
 *   - the section is absent once a coach is assigned
 *   - the section is absent in coach/admin mirror view (onboarding never fetched)
 *   - the Reminders rhythm row carries a WhatsApp/Text toggle bound to
 *     contact_method (client-self only), PATCHing quietly on change
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { HomePage } from "./HomePage";

const state = vi.hoisted(() => ({
  user: null,
  filter: null,
  responses: {},
  apiCalls: [],
  patchCalls: [],
}));

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn((url) => {
      state.apiCalls.push(url);
      if (url in state.responses) {
        return Promise.resolve({ data: state.responses[url] });
      }
      return Promise.reject(new Error(`no mock response for ${url}`));
    }),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    patch: vi.fn((url, body) => {
      state.patchCalls.push({ url, body });
      return Promise.resolve({ data: { ...state.responses[url], ...body } });
    }),
  },
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: state.user, updateUser: vi.fn(), logout: vi.fn() }),
}));

vi.mock("../filters/ClientFilterContext", () => ({
  useClientFilter: () => state.filter,
}));

const COACH = {
  name: "Sam Reyes",
  photo_url: null,
  bio: "Here to help you find your rhythm.",
  contact_email: "sam@getupandflow.com",
  contact_phone: null,
};

const ONBOARDING = {
  timezone: "America/New_York",
  morning_window: "6-8am",
  evening_window: "6-8pm",
  contact_method: "whatsapp",
  contact_number: "+1 555 0199",
  help_topics: "Getting mornings started without spiraling.",
  help_topics_seed: "",
  completed_at: "2026-07-20T12:00:00Z",
};

function useClientSelf({
  coach = null,
  helpTopics = ONBOARDING.help_topics,
  helpTopicsSeed = "",
  contactMethod = ONBOARDING.contact_method,
} = {}) {
  state.user = {
    id: 1,
    role: "Client",
    first_name: "Ava",
    last_name: "Stone",
    username: "ava",
    email: "ava@example.com",
    onboarding_complete: true,
    my_coach: coach,
  };
  state.filter = {
    clients: [],
    events: [],
    isLoadingClients: false,
    selectedClients: [],
    selectedClientIds: [],
    supportsClientFiltering: false,
  };
  state.responses = {
    "/billing/subscription/": { status: "active" },
    "/onboarding/": {
      ...ONBOARDING,
      help_topics: helpTopics,
      help_topics_seed: helpTopicsSeed,
      contact_method: contactMethod,
    },
  };
}

function useCoachMirror({ clientCoach = null } = {}) {
  state.user = {
    id: 2,
    role: "Coach",
    first_name: "Sam",
    last_name: "Reyes",
    username: "sam",
    email: "sam@getupandflow.com",
    profile: {},
  };
  const client = { id: 5, label: "Ava Stone", coach: clientCoach };
  state.filter = {
    clients: [client],
    events: [],
    isLoadingClients: false,
    selectedClients: [client],
    selectedClientIds: [5],
    supportsClientFiltering: true,
  };
  state.responses = {};
}

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  );
}

const GOALS_LABEL = "What I want help with";
const GOALS_EXPLAINER =
  "This is what you shared when you signed up. Add to it any time — everything here shapes your match.";
const CHANNEL_GROUP = "How reminders reach you";

async function findGoalsForm() {
  const textarea = await screen.findByLabelText(GOALS_LABEL);
  return { textarea, form: within(textarea.closest("form")) };
}

beforeEach(() => {
  state.apiCalls = [];
  state.patchCalls = [];
});

describe("Goals section (unassigned client-self)", () => {
  it("shows the saved goals text with the resume explainer and persists an edit via PATCH", async () => {
    useClientSelf();
    renderHome();

    const { textarea, form } = await findGoalsForm();
    expect(textarea).toHaveValue("Getting mornings started without spiraling.");
    expect(screen.getByText(GOALS_EXPLAINER)).toBeInTheDocument();

    fireEvent.change(textarea, {
      target: { value: "Mornings, and staying with one task at a time." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(state.patchCalls).toEqual([
        {
          url: "/onboarding/",
          body: { help_topics: "Mornings, and staying with one task at a time." },
        },
      ]),
    );

    // Quiet confirmation, cleared again as soon as the text changes.
    await waitFor(() => expect(form.getByRole("status")).toHaveTextContent(/Saved/));
    fireEvent.change(textarea, { target: { value: "Mornings." } });
    expect(form.getByRole("status")).toBeEmptyDOMElement();
  });

  it("seeds an empty answer from the marketing lead message, persisting only on Save", async () => {
    useClientSelf({ helpTopics: "", helpTopicsSeed: "Mornings are the hard part." });
    renderHome();

    const { textarea } = await findGoalsForm();
    expect(textarea).toHaveValue("Mornings are the hard part.");
    // Read-only seed: nothing has been written yet.
    expect(state.patchCalls).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(state.patchCalls).toEqual([
        { url: "/onboarding/", body: { help_topics: "Mornings are the hard part." } },
      ]),
    );
  });

  it("invites a first pass when there is no saved text and no seed", async () => {
    useClientSelf({ helpTopics: "" });
    renderHome();

    const { textarea } = await findGoalsForm();
    expect(textarea).toHaveValue("");
    expect(textarea).toHaveAttribute("placeholder", expect.stringMatching(/a good place to start/));
  });
});

describe("Goals section (absent elsewhere)", () => {
  it("is absent once a coach is assigned", async () => {
    useClientSelf({ coach: COACH });
    renderHome();

    expect(await screen.findByText("Sam Reyes")).toBeInTheDocument();
    expect(screen.queryByText(GOALS_LABEL)).not.toBeInTheDocument();
    expect(screen.queryByText("Your coach is on the way")).not.toBeInTheDocument();
  });

  it("is absent in mirror view even for an unassigned client, with no onboarding fetch", async () => {
    useCoachMirror({ clientCoach: null });
    renderHome();

    expect(await screen.findByText(/Good (morning|afternoon|evening), Ava/)).toBeInTheDocument();
    expect(screen.queryByText(GOALS_LABEL)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(state.apiCalls).not.toContain("/onboarding/");
  });
});

describe("Reminders channel toggle", () => {
  it("reflects the saved contact_method and PATCHes quietly on change", async () => {
    useClientSelf({ coach: COACH, contactMethod: "whatsapp" });
    renderHome();

    const group = await screen.findByRole("group", { name: CHANNEL_GROUP });
    const whatsapp = within(group).getByRole("button", { name: "WhatsApp" });
    const text = within(group).getByRole("button", { name: "Text" });
    expect(whatsapp).toHaveAttribute("aria-pressed", "true");
    expect(text).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(text);
    await waitFor(() =>
      expect(state.patchCalls).toEqual([
        { url: "/onboarding/", body: { contact_method: "sms" } },
      ]),
    );
    await waitFor(() => expect(text).toHaveAttribute("aria-pressed", "true"));
    expect(within(group.parentElement).getByRole("status")).toHaveTextContent("Saved");
  });

  it("does not PATCH when the already-selected channel is clicked", async () => {
    useClientSelf({ coach: COACH, contactMethod: "sms" });
    renderHome();

    const group = await screen.findByRole("group", { name: CHANNEL_GROUP });
    fireEvent.click(within(group).getByRole("button", { name: "Text" }));
    expect(state.patchCalls).toEqual([]);
    expect(within(group.parentElement).getByRole("status")).toBeEmptyDOMElement();
  });

  it("is absent in coach/admin mirror view", async () => {
    useCoachMirror({ clientCoach: COACH });
    renderHome();

    expect(await screen.findByText(/Good (morning|afternoon|evening), Ava/)).toBeInTheDocument();
    expect(screen.getByText("Reminders")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: CHANNEL_GROUP })).not.toBeInTheDocument();
  });
});
