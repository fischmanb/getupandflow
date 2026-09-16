/** Timezone choices, sourced from the runtime's own IANA database.
 *
 * No hardcoded list: Intl.supportedValuesOf gives every zone the browser knows.
 * Older browsers without it fall back to the resolved local zone alone, which
 * is always enough to submit the form correctly.
 */
export function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

export function timezoneOptions() {
  let all = [];
  try {
    all = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  } catch {
    all = [];
  }
  const local = browserTimezone();
  if (!all.length) return local ? [local] : [];
  return all.includes(local) || !local ? all : [local, ...all];
}

/** "America/New_York" -> "America / New York (GMT-4)" for the select label. */
export function timezoneLabel(name) {
  let offset = "";
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: name,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date());
    offset = parts.find((part) => part.type === "timeZoneName")?.value || "";
  } catch {
    offset = "";
  }
  const pretty = name.replace(/_/g, " ").replace("/", " / ");
  return offset ? `${pretty} (${offset})` : pretty;
}
