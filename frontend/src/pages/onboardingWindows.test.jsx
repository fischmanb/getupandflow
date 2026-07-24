/**
 * Onboarding window selectors (hourly since 2026-07):
 *   - a fresh form offers hourly choices only
 *   - a record saved with a legacy 2-hour block keeps that value selected and
 *     rendered as stored (prepended option), alongside the hourly choices
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { OnboardingPage } from "./OnboardingPage";

const state = vi.hoisted(() => ({ onboarding: null }));

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(() => Promise.resolve({ data: state.onboarding })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
  },
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, role: "Client", username: "ava" },
    updateUser: vi.fn(),
    logout: vi.fn(),
  }),
}));

function renderOnboarding() {
  return render(
    <MemoryRouter>
      <OnboardingPage />
    </MemoryRouter>,
  );
}

function optionValues(select) {
  return within(select)
    .getAllByRole("option")
    .map((option) => option.value)
    .filter(Boolean); // drop the "Choose a window" placeholder
}

beforeEach(() => {
  state.onboarding = null;
});

describe("Onboarding check-in window choices", () => {
  it("offers hourly windows only on a fresh form", async () => {
    renderOnboarding();

    const morning = await screen.findByLabelText("Preferred morning check-in");
    const evening = screen.getByLabelText("Preferred evening check-in");

    expect(optionValues(morning)).toEqual([
      "6-7am",
      "7-8am",
      "8-9am",
      "9-10am",
      "10-11am",
      "11am-12pm",
    ]);
    expect(optionValues(evening)).toEqual([
      "4-5pm",
      "5-6pm",
      "6-7pm",
      "7-8pm",
      "8-9pm",
      "9-10pm",
    ]);
  });

  it("keeps a saved legacy block value selected and rendered as stored", async () => {
    state.onboarding = {
      timezone: "UTC",
      morning_window: "8-10am",
      evening_window: "6-8pm",
      contact_method: "whatsapp",
      contact_number: "+1 555 0199",
      help_topics: "",
      completed_at: "2026-07-01T12:00:00Z",
    };
    renderOnboarding();

    const morning = await screen.findByLabelText("Preferred morning check-in");
    expect(morning).toHaveValue("8-10am");
    expect(within(morning).getByRole("option", { name: "8:00–10:00 am" })).toBeInTheDocument();
    // The hourly choices are still all there behind the stored legacy value.
    expect(optionValues(morning)).toEqual([
      "8-10am",
      "6-7am",
      "7-8am",
      "8-9am",
      "9-10am",
      "10-11am",
      "11am-12pm",
    ]);

    const evening = screen.getByLabelText("Preferred evening check-in");
    expect(evening).toHaveValue("6-8pm");
    expect(within(evening).getByRole("option", { name: "6:00–8:00 pm" })).toBeInTheDocument();
  });

  it("does not inject a legacy option when the saved value is hourly", async () => {
    state.onboarding = {
      timezone: "UTC",
      morning_window: "7-8am",
      evening_window: "8-9pm",
      contact_method: "sms",
      contact_number: "+1 555 0199",
      help_topics: "",
      completed_at: "2026-07-01T12:00:00Z",
    };
    renderOnboarding();

    const morning = await screen.findByLabelText("Preferred morning check-in");
    expect(morning).toHaveValue("7-8am");
    expect(optionValues(morning)).toHaveLength(6);
  });
});
