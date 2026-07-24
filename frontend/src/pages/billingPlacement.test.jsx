/**
 * Billing placement contract (home makeover):
 *   - billing controls are absent from Home (client-self AND mirror view)
 *   - billing controls render in Account Settings for the client-self only
 *   - Home keeps a quiet past-due notice with no plan controls
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { AccountSettingsPage } from "./AccountSettingsPage";
import { HomePage } from "./HomePage";

const state = vi.hoisted(() => ({
  user: null,
  filter: null,
  responses: {},
  apiCalls: [],
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
    patch: vi.fn(() => Promise.resolve({ data: {} })),
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

const ACTIVE_SUBSCRIPTION = {
  plan_name: "Full Support",
  amount: "750",
  interval: "monthly",
  status: "active",
  cancel_at_period_end: false,
  current_period_end: "2026-08-01T00:00:00Z",
  card_brand: "visa",
  card_last4: "4242",
};

function useClientSelf({ subscription = ACTIVE_SUBSCRIPTION, events = [] } = {}) {
  state.user = {
    id: 1,
    role: "Client",
    first_name: "Ava",
    last_name: "Stone",
    username: "ava",
    email: "ava@example.com",
    onboarding_complete: true,
    my_coach: COACH,
  };
  state.filter = {
    clients: [],
    events,
    isLoadingClients: false,
    selectedClients: [],
    selectedClientIds: [],
    supportsClientFiltering: false,
  };
  state.responses = {
    "/billing/subscription/": subscription,
    "/onboarding/": {
      timezone: "America/New_York",
      morning_window: "6-8am",
      evening_window: "6-8pm",
    },
  };
}

function useCoachMirror() {
  state.user = {
    id: 2,
    role: "Coach",
    first_name: "Sam",
    last_name: "Reyes",
    username: "sam",
    email: "sam@getupandflow.com",
    profile: {},
  };
  state.filter = {
    clients: [{ id: 5, label: "Ava Stone", coach: COACH }],
    events: [],
    isLoadingClients: false,
    selectedClients: [{ id: 5, label: "Ava Stone", coach: COACH }],
    selectedClientIds: [5],
    supportsClientFiltering: true,
  };
  state.responses = {};
}

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

function expectNoBillingControls() {
  expect(screen.queryByText("Billing")).not.toBeInTheDocument();
  expect(screen.queryByText("Cancel plan")).not.toBeInTheDocument();
  expect(screen.queryByText("Change plan")).not.toBeInTheDocument();
  expect(screen.queryByText("Update payment method")).not.toBeInTheDocument();
  expect(screen.queryByText("Manage billing")).not.toBeInTheDocument();
}

beforeEach(() => {
  state.apiCalls = [];
});

describe("HomePage (client-self)", () => {
  it("shows the members' room without any billing controls", async () => {
    useClientSelf();
    renderWithRouter(<HomePage />);

    expect(await screen.findByText(/Good (morning|afternoon|evening), Ava/)).toBeInTheDocument();
    expect(screen.getByText("Sam Reyes")).toBeInTheDocument();

    // Rhythm windows come from the client's own onboarding prefs. These are
    // legacy 2-hour block values — they must keep rendering as stored now
    // that the choices are hourly.
    expect(await screen.findByText("Mornings, 6:00–8:00 am")).toBeInTheDocument();
    expect(screen.getByText("Evenings, 6:00–8:00 pm")).toBeInTheDocument();

    // Subscription was fetched (past-due detection) but no controls render.
    await waitFor(() => expect(state.apiCalls).toContain("/billing/subscription/"));
    expectNoBillingControls();

    // Discreet route to billing instead.
    const settingsLink = screen.getByRole("link", { name: "Account & billing" });
    expect(settingsLink).toHaveAttribute("href", "/app/settings");

    // No upcoming event -> the next-session line is omitted entirely.
    expect(screen.queryByText(/Next session/)).not.toBeInTheDocument();
  });

  it("shows a quiet past-due notice with no plan controls", async () => {
    useClientSelf({ subscription: { ...ACTIVE_SUBSCRIPTION, status: "past_due" } });
    renderWithRouter(<HomePage />);

    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent(/problem with your last payment/);

    const noticeLink = screen.getByRole("link", { name: /review billing in account settings/ });
    expect(noticeLink).toHaveAttribute("href", "/app/settings");

    // The portal-redirect button from the full banner must NOT be on Home.
    expect(screen.queryByRole("button", { name: /update your payment method/ })).not.toBeInTheDocument();
    expectNoBillingControls();
  });

  it("renders hourly check-in windows in the rhythm block", async () => {
    useClientSelf();
    state.responses["/onboarding/"] = {
      timezone: "America/New_York",
      morning_window: "7-8am",
      evening_window: "8-9pm",
    };
    renderWithRouter(<HomePage />);

    expect(await screen.findByText("Mornings, 7:00–8:00 am")).toBeInTheDocument();
    expect(screen.getByText("Evenings, 8:00–9:00 pm")).toBeInTheDocument();
  });

  it("shows the next session as one quiet line when an upcoming event exists", async () => {
    const future = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    const isoDate = `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(future.getDate())}`;
    useClientSelf({
      events: [
        { id: 9, title: "Session", event_date: isoDate, start_time: "15:00:00", end_time: "15:45:00" },
      ],
    });
    renderWithRouter(<HomePage />);

    expect(await screen.findByText(/Next session:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "view calendar" })).toHaveAttribute("href", "/app/calendar");
  });
});

describe("HomePage (coach/admin mirror view)", () => {
  it("mirrors the client's home with no billing and no billing fetch", async () => {
    useCoachMirror();
    renderWithRouter(<HomePage />);

    expect(await screen.findByText(/Good (morning|afternoon|evening), Ava/)).toBeInTheDocument();
    expect(screen.getByText("Sam Reyes")).toBeInTheDocument();

    expectNoBillingControls();
    expect(screen.queryByRole("link", { name: "Account & billing" })).not.toBeInTheDocument();
    expect(state.apiCalls).not.toContain("/billing/subscription/");
    expect(state.apiCalls).not.toContain("/onboarding/");
  });
});

describe("AccountSettingsPage", () => {
  it("renders the full billing card with plan controls for the client-self", async () => {
    useClientSelf();
    renderWithRouter(<AccountSettingsPage />);

    expect(await screen.findByText("Billing")).toBeInTheDocument();
    expect(screen.getByText("Full Support")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update payment method" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Manage billing" })).toBeInTheDocument();
  });

  it("renders no billing section for a coach", async () => {
    useCoachMirror();
    renderWithRouter(<AccountSettingsPage />);

    expect(await screen.findByText("Your account")).toBeInTheDocument();
    expectNoBillingControls();
    expect(state.apiCalls).not.toContain("/billing/subscription/");
  });
});
