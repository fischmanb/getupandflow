/** Timezone choices, sourced from the runtime's own IANA database.
 *
 * No hardcoded list: Intl.supportedValuesOf gives every zone the browser knows.
 * The list is only the menu; the applicant picks. Nothing here reads or
 * defaults to the device's own zone setting.
 */
export function timezoneOptions() {
  try {
    return typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  } catch {
    return [];
  }
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
