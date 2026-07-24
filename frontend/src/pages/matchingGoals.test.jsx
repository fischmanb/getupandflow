/**
 * Matching-phase goals editing contract (home makeover addendum):
 *   - while a client-self is unassigned, the matching card carries an editable
 *     "What I want help with" block that PATCHes the existing onboarding record
 *   - the block is absent once a coach is assigned
 *   - the block is absent in coach/admin mirror view (onboarding never fetched)
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  completed_at: "2026-07-20T12:00:00Z",
};

function useClientSelf({ coach = null, helpTopics = ONBOARDING.help_topics } = {}) {
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
    "/onboarding/": { ...ONBOARDING, help_topics: helpTopics },
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

beforeEach(() => {
  state.apiCalls = [];
  state.patchCalls = [];
});

describe("Matching card goals block (unassigned client-self)", () => {
  it("shows the saved goals text and persists an edit via PATCH /onboarding/", async () => {
    useClientSelf();
    renderHome();

    const textarea = await screen.findByLabelText(GOALS_LABEL);
    expect(textarea).toHaveValue("Getting mornings started without spiraling.");
    expect(screen.getByText("The more you share, the better we match you.")).toBeInTheDocument();

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
    expect(await screen.findByRole("status")).toHaveTextContent(/Saved/);
    fireEvent.change(textarea, { target: { value: "Mornings." } });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("invites a first pass when the goals text is empty", async () => {
    useClientSelf({ helpTopics: "" });
    renderHome();

    const textarea = await screen.findByLabelText(GOALS_LABEL);
    expect(textarea).toHaveValue("");
    expect(textarea).toHaveAttribute("placeholder", expect.stringMatching(/a good place to start/));
  });
});

describe("Matching card goals block (absent elsewhere)", () => {
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
