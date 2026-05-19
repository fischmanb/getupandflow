import { useEffect, useState } from "react";

import { EventCalendar } from "./EventCalendar";
import { EventFormPanel } from "./EventFormPanel";
import { useClientFilter } from "../filters/ClientFilterContext";

function getEventPromptMessage(selectedClientCount) {
  if (selectedClientCount === 0) {
    return "Select one client before creating an event.";
  }

  return "Select exactly one client before creating an event.";
}

export function CalendarPanel({ className }) {
  const { colorMap, eventError, events, isLoadingEvents, refreshEvents, selectedClientIds, supportsClientFiltering } =
    useClientFilter();
  const [isCreating, setIsCreating] = useState(false);
  const [editingEvent, setEditingEvent] = useState(null);
  const [createPromptMessage, setCreatePromptMessage] = useState("");
  const [createInitialDate, setCreateInitialDate] = useState("");
  const canCreateForSelection = !supportsClientFiltering || selectedClientIds.length === 1;

  useEffect(() => {
    if (canCreateForSelection) {
      setCreatePromptMessage("");
    }
  }, [canCreateForSelection]);

  function closeForms() {
    setIsCreating(false);
    setEditingEvent(null);
    setCreateInitialDate("");
  }

  async function handleSaved() {
    closeForms();
    await refreshEvents();
  }

  function beginCreate(initialDate = "") {
    if (!canCreateForSelection) {
      setCreatePromptMessage(getEventPromptMessage(selectedClientIds.length));
      return;
    }

    setCreatePromptMessage("");
    setCreateInitialDate(initialDate);
    setIsCreating(true);
    setEditingEvent(null);
  }

  return (
    <article className={className}>
      {createPromptMessage ? <p className="calendar-create-error">{createPromptMessage}</p> : null}
      {isCreating || editingEvent ? (
        <EventFormPanel
          event={editingEvent}
          initialDate={createInitialDate}
          onCancel={closeForms}
          onSaved={handleSaved}
        />
      ) : null}
      {eventError ? <p className="form-error">{eventError}</p> : null}
      {isLoadingEvents ? (
        <p className="subtle-copy">Loading calendar events...</p>
      ) : (
        <EventCalendar
          colorMap={colorMap}
          events={events}
          onCreateForDate={beginCreate}
          onSelectEvent={setEditingEvent}
        />
      )}
    </article>
  );
}
