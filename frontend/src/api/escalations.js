import { apiClient } from "./client";

// Leadership-gated escalation queue. Ordering + breach math are the server's;
// the client only renders what /api/escalations/ returns.

// The Archive tab reads only archived (closed) rows; every other tab reads the
// live queue by lifecycle status.
export async function fetchEscalations(filterKey) {
  const params =
    filterKey === "archive" ? { archived: "true" } : filterKey ? { status: filterKey } : {};
  const { data } = await apiClient.get("/escalations/", { params });
  // The API paginates; the queue reads the results array.
  return data.results ?? data;
}

export async function fetchEscalationDetail(id) {
  const { data } = await apiClient.get(`/escalations/${id}/`);
  return data;
}

// The active resolution vocabulary (Bruce's editable list) for the close sheet.
export async function fetchResolutionMethods() {
  const { data } = await apiClient.get("/escalations/methods/");
  return data.results ?? data;
}

// note / resolutionMethod / resolutionNote are all optional; closing moves
// require resolutionMethod (and a note when the method is "other").
export async function transitionEscalation(id, toStatus, opts = {}) {
  const { data } = await apiClient.post(`/escalations/${id}/transition/`, {
    to_status: toStatus,
    note: opts.note || "",
    resolution_method: opts.resolutionMethod || undefined,
    resolution_note: opts.resolutionNote || "",
  });
  return data;
}

// Leadership-only reopen of an archived escalation back into review (audited).
export async function reopenEscalation(id, note) {
  const { data } = await apiClient.post(`/escalations/${id}/reopen/`, {
    note: note || "",
  });
  return data;
}
