import { apiClient } from "./client";

// Leadership-gated escalation queue. Ordering + breach math are the server's;
// the client only renders what /api/escalations/ returns.

export async function fetchEscalations(statusFilter) {
  const params = statusFilter ? { status: statusFilter } : {};
  const { data } = await apiClient.get("/escalations/", { params });
  // The API paginates; the queue reads the results array.
  return data.results ?? data;
}

export async function fetchEscalationDetail(id) {
  const { data } = await apiClient.get(`/escalations/${id}/`);
  return data;
}

export async function transitionEscalation(id, toStatus, note) {
  const { data } = await apiClient.post(`/escalations/${id}/transition/`, {
    to_status: toStatus,
    note: note || "",
  });
  return data;
}
