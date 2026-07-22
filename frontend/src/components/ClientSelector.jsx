import { useClientFilter } from "../filters/ClientFilterContext";

export function ClientSelector() {
  const {
    clientError,
    clients,
    colorMap,
    isClientSelected,
    isLoadingClients,
    selectedClientIds,
    supportsClientFiltering,
    toggleClient,
  } = useClientFilter();

  if (!supportsClientFiltering) {
    return null;
  }

  return (
    <section className="client-selector">
      <div className="client-selector-header">
        <p className="menu-section-title">Show calendars for</p>
        <span className="client-selector-count">{selectedClientIds.length}</span>
      </div>
      {isLoadingClients ? <p className="subtle-copy">Loading clients...</p> : null}
      {clientError ? <p className="form-error">{clientError}</p> : null}
      {!isLoadingClients ? (
        <div className="client-selector-list">
          {clients.map((client) => {
            const isSelected = isClientSelected(client.id);
            const accentColor = colorMap[client.id];
            const labelIsAmbiguous =
              client.label !== client.username &&
              clients.some((other) => other.id !== client.id && other.label === client.label);

            return (
              <label
                key={client.id}
                className={isSelected ? "client-option client-option-selected" : "client-option"}
                style={{ "--client-accent": accentColor }}
              >
                <input
                  checked={isSelected}
                  onChange={() => toggleClient(client.id)}
                  type="checkbox"
                />
                <span className="client-option-swatch" />
                <span className="client-option-text">
                  <strong>{client.label}</strong>
                  {labelIsAmbiguous ? <small>{"@" + client.username}</small> : null}
                </span>
              </label>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
