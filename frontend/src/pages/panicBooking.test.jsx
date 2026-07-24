/**
 * Panic Button booking contract (.tasks/panic-booking.md):
 *   - /app/panic is client-self only; matching-state clients get the calm
 *     unassigned message and a route home
 *   - slots come from panic-availability and book via tap (server-validated)
 *   - a 409 conflict renders the suggested times as one-tap choices
 *   - remaining minutes + today's sessions (with cancel) are shown
 *   - Home: the Panic Button touchpoint links to /app/panic for the client
 *     only — mirror view keeps the calendar link
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { HomePage } from "./HomePage";
import { PanicPage } from "./PanicPage";

const state = vi.hoisted(() => ({
  user: null,
  filter: null,
  responses: {},
  apiCalls: [],
}));

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("../api/client", () => ({ apiClient: apiMock }));

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

const AVAILABILITY = {
  duration: 15,
  timezone: "America/New_York",
  cap_minutes: 45,
  remaining_minutes_today: 30,
  days: [
    {
      date: "2026-07-29",
      slots: [{ start_at: "2026-07-29T10:30:00-04:00" }, { start_at: "2026-07-29T10:45:00-04:00" }],
    },
    { date: "2026-07-30", slots: [{ start_at: "2026-07-30T08:00:00-04:00" }] },
  ],
  next_bookable_at: null,
};

const SESSIONS = {
  timezone: "America/New_York",
  cap_minutes: 45,
  remaining_minutes_today: 30,
  sessions: [
    {
      id: 7,
      start_at: "2026-07-29T15:00:00-04:00",
      end_at: "2026-07-29T15:15:00-04:00",
      duration_minutes: 15,
      note: "",
      meeting_link: "",
      can_cancel: true,
    },
  ],
};

const BOOKED = {
  id: 9,
  start_at: "2026-07-29T10:30:00-04:00",
  end_at: "2026-07-29T10:45:00-04:00",
  duration_minutes: 15,
  note: "",
  meeting_link: "",
  can_cancel: true,
  zoom_status: "ok",
  timezone: "America/New_York",
};

function useClientSelf({ coach = COACH } = {}) {
  state.user = {
    id: 1,
    role: "Client",
    first_name: "Ava",
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
    "/panic-availability/": AVAILABILITY,
    "/panic-sessions/": SESSIONS,
    "/billing/subscription/": { status: "active" },
    "/onboarding/": { timezone: "America/New_York", morning_window: "8-9am", evening_window: "6-7pm" },
  };
}

function useCoachMirror() {
  state.user = { id: 2, role: "Coach", first_name: "Sam", username: "sam", profile: {} };
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

beforeEach(() => {
  state.apiCalls = [];
  apiMock.get.mockReset().mockImplementation((url) => {
    state.apiCalls.push(url);
    if (url in state.responses) {
      return Promise.resolve({ data: state.responses[url] });
    }
    return Promise.reject(new Error(`no mock response for ${url}`));
  });
  apiMock.post.mockReset().mockResolvedValue({ data: BOOKED });
  apiMock.patch.mockReset().mockResolvedValue({ data: {} });
  apiMock.delete.mockReset().mockResolvedValue({ data: {} });
});

describe("PanicPage gates", () => {
  it("shows the calm unassigned message while matching, without fetching slots", () => {
    useClientSelf({ coach: null });
    renderWithRouter(<PanicPage />);

    expect(screen.getByText(/Stuck is normal/)).toBeInTheDocument();
    expect(screen.getByText(/matching you now/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back home" })).toHaveAttribute("href", "/app");
    expect(state.apiCalls).not.toContain("/panic-availability/");
    expect(state.apiCalls).not.toContain("/panic-sessions/");
  });
});

describe("PanicPage booking", () => {
  it("books a tapped slot and shows the quiet confirmation", async () => {
    useClientSelf();
    renderWithRouter(<PanicPage />);

    // The reassuring line, remaining minutes, and today's booked session.
    expect(screen.getByText("Stuck is normal. Grab your coach.")).toBeInTheDocument();
    expect(await screen.findByText("You have 30 panic minutes left today.")).toBeInTheDocument();
    expect(screen.getByText(/3:00 pm · 15 min/)).toBeInTheDocument();

    // Day tabs from the availability payload (fixed dates -> weekday labels).
    expect(screen.getByRole("tab", { name: "Wednesday" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Thursday" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "10:30 am" }));
    fireEvent.click(screen.getByRole("button", { name: "Book it" }));

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith("/panic-sessions/", {
        duration: 15,
        start_time: "2026-07-29T10:30:00-04:00",
      }),
    );

    expect(await screen.findByText(/You're booked — Wednesday, July 29 at 10:30 am/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See it on your calendar" })).toHaveAttribute(
      "href",
      "/app/calendar",
    );
  });

  it("refetches slots for the chosen duration", async () => {
    useClientSelf();
    renderWithRouter(<PanicPage />);
    await screen.findByRole("button", { name: "10:30 am" });

    fireEvent.click(screen.getByRole("button", { name: "30 minutes" }));

    await waitFor(() =>
      expect(apiMock.get).toHaveBeenCalledWith("/panic-availability/", { params: { duration: 30 } }),
    );
  });

  it("renders 409 suggestions as one-tap choices that book directly", async () => {
    useClientSelf();
    apiMock.post
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: {
            detail: "Your coach is already booked then — here are the closest open times.",
            suggestions: ["2026-07-29T10:45:00-04:00"],
          },
        },
      })
      .mockResolvedValue({ data: { ...BOOKED, start_at: "2026-07-29T10:45:00-04:00" } });

    renderWithRouter(<PanicPage />);
    fireEvent.click(await screen.findByRole("button", { name: "10:30 am" }));
    fireEvent.click(screen.getByRole("button", { name: "Book it" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/already booked then/);

    fireEvent.click(screen.getByRole("button", { name: "Wednesday, July 29 at 10:45 am" }));

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenLastCalledWith("/panic-sessions/", {
        duration: 15,
        start_time: "2026-07-29T10:45:00-04:00",
      }),
    );
    expect(await screen.findByText(/You're booked — Wednesday, July 29 at 10:45 am/)).toBeInTheDocument();
  });

  it("cancels an upcoming session", async () => {
    useClientSelf();
    renderWithRouter(<PanicPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith("/panic-sessions/7/"));
  });

  it("says so plainly when the window has no bookable times", async () => {
    useClientSelf();
    state.responses["/panic-availability/"] = {
      ...AVAILABILITY,
      days: [],
      next_bookable_at: "2026-08-03T08:00:00-04:00",
    };
    renderWithRouter(<PanicPage />);

    expect(await screen.findByText(/No open times in the next 48 hours/)).toBeInTheDocument();
    expect(screen.getByText(/next bookable day is Monday/)).toBeInTheDocument();
  });
});

describe("Home rhythm block touchpoint", () => {
  it("links the Panic Button touchpoint to /app/panic for the client", async () => {
    useClientSelf();
    renderWithRouter(<HomePage />);

    const panicLink = await screen.findByRole("link", { name: "grab a panic session" });
    expect(panicLink).toHaveAttribute("href", "/app/panic");
  });

  it("keeps the calendar link in coach/admin mirror view (no /app/panic)", async () => {
    useCoachMirror();
    renderWithRouter(<HomePage />);

    await screen.findByText(/Good (morning|afternoon|evening), Ava/);
    expect(screen.queryByRole("link", { name: "grab a panic session" })).not.toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.some((link) => link.getAttribute("href") === "/app/panic")).toBe(false);
    expect(screen.getByRole("link", { name: "open your calendar" })).toHaveAttribute(
      "href",
      "/app/calendar",
    );
  });
});
