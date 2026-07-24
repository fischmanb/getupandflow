// Check-in window choices, shared by the onboarding form and the Home rhythm
// editors. Hourly is what we offer now; the legacy 2-hour blocks stay mapped
// so rows saved before the change render as stored (no forced data migration).
export const MORNING_WINDOWS = [
  ["6-7am", "6:00–7:00 am"],
  ["7-8am", "7:00–8:00 am"],
  ["8-9am", "8:00–9:00 am"],
  ["9-10am", "9:00–10:00 am"],
  ["10-11am", "10:00–11:00 am"],
  ["11am-12pm", "11:00 am–12:00 pm"],
];

export const EVENING_WINDOWS = [
  ["4-5pm", "4:00–5:00 pm"],
  ["5-6pm", "5:00–6:00 pm"],
  ["6-7pm", "6:00–7:00 pm"],
  ["7-8pm", "7:00–8:00 pm"],
  ["8-9pm", "8:00–9:00 pm"],
  ["9-10pm", "9:00–10:00 pm"],
];

// Legacy 2-hour blocks: still stored on accounts onboarded before the hourly
// change and still accepted by the backend. Never offered to new signups —
// but a saved legacy answer must keep rendering as stored (see savedFirst).
export const LEGACY_WINDOW_LABELS = {
  "6-8am": "6:00–8:00 am",
  "8-10am": "8:00–10:00 am",
  "10am-12pm": "10:00 am–12:00 pm",
  "4-6pm": "4:00–6:00 pm",
  "6-8pm": "6:00–8:00 pm",
  "8-10pm": "8:00–10:00 pm",
};

const ALL_WINDOW_LABELS = {
  ...Object.fromEntries(MORNING_WINDOWS),
  ...Object.fromEntries(EVENING_WINDOWS),
  ...LEGACY_WINDOW_LABELS,
};

export function windowLabel(value) {
  return ALL_WINDOW_LABELS[value] || value;
}

// Prepend the saved value as an extra option when it isn't in the hourly list,
// so a legacy answer stays visible and resubmittable instead of blanking out.
export function savedFirst(options, saved) {
  if (!saved || options.some(([value]) => value === saved)) return options;
  return [[saved, LEGACY_WINDOW_LABELS[saved] || saved], ...options];
}
