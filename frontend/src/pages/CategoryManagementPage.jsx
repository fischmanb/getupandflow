import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../api/client";
import { getErrorMessage, getListData, getPaginationMeta } from "../api/utils";
import { useAuth } from "../auth/AuthContext";
import { PRESET_CATEGORY_COLORS, getCategoryColorHex } from "../categories/presetColors";
import { PaginationControls } from "../components/PaginationControls";
import { useClientFilter } from "../filters/ClientFilterContext";

function getInitialFormState(category) {
  return {
    name: category?.name || "",
    color: category?.color || PRESET_CATEGORY_COLORS[0].value,
  };
}

export function CategoryManagementPage() {
  const { user } = useAuth();
  const { clients: availableClients, supportsClientFiltering } = useClientFilter();

  const [categories, setCategories] = useState([]);
  const [editingCategory, setEditingCategory] = useState(null);
  const [formState, setFormState] = useState(getInitialFormState(null));
  const [selectedClientId, setSelectedClientId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingCategories, setIsLoadingCategories] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [listErrorMessage, setListErrorMessage] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);

  // Coaches and Admins must pick which client they're managing categories for.
  // Clients are themselves — no picker needed.
  const isManagingOnBehalf = supportsClientFiltering;
  const effectiveClientId = isManagingOnBehalf ? selectedClientId : user?.id;

  // Default-select the first available client when the picker first becomes relevant.
  useEffect(() => {
    if (isManagingOnBehalf && !selectedClientId && availableClients.length > 0) {
      setSelectedClientId(availableClients[0].id);
    }
  }, [availableClients, isManagingOnBehalf, selectedClientId]);

  async function loadCategories(page = currentPage) {
    if (isManagingOnBehalf && !effectiveClientId) {
      // No client picked yet; show empty.
      setCategories([]);
      setTotalPages(0);
      setIsLoadingCategories(false);
      return;
    }
    setIsLoadingCategories(true);
    setListErrorMessage("");
    try {
      const params = { page };
      if (isManagingOnBehalf) params.client_id = effectiveClientId;
      const response = await apiClient.get("/categories/", { params });
      setCategories(getListData(response.data));
      setTotalPages(getPaginationMeta(response.data).totalPages);
      setCurrentPage(page);
    } catch (error) {
      setCategories([]);
      setTotalPages(0);
      setListErrorMessage(getErrorMessage(error, "We couldn't load categories right now."));
    } finally {
      setIsLoadingCategories(false);
    }
  }

  // Reload whenever the picked client changes.
  useEffect(() => {
    loadCategories(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveClientId]);

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");

    if (isManagingOnBehalf && !effectiveClientId) {
      setErrorMessage("Pick a client before saving a category.");
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = { ...formState };
      // Coaches/Admins always send client_id; Clients omit it (server defaults to self).
      if (isManagingOnBehalf) payload.client_id = effectiveClientId;

      if (editingCategory) {
        await apiClient.patch(`/categories/${editingCategory.id}/`, formState);
      } else {
        await apiClient.post("/categories/", payload);
      }
      setEditingCategory(null);
      setFormState(getInitialFormState(null));
      await loadCategories(1);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Unable to save category."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(categoryId) {
    setListErrorMessage("");
    try {
      await apiClient.delete(`/categories/${categoryId}/`);
      if (editingCategory?.id === categoryId) {
        setEditingCategory(null);
        setFormState(getInitialFormState(null));
      }
      await loadCategories(1);
    } catch (error) {
      setListErrorMessage(getErrorMessage(error, "Unable to delete category."));
    }
  }

  const headerCopy = useMemo(() => {
    if (!isManagingOnBehalf) {
      return "Categories are only used for events and must use one of the preset colors.";
    }
    return "Categories belong to a client. Pick the client whose categories you're managing.";
  }, [isManagingOnBehalf]);

  return (
    <main className="content-page">
      <section className="content-card">
        <Link className="back-link" to="/app">← Back</Link>
        <p className="eyebrow">Event Categories</p>
        <h2>Manage event categories</h2>
        <p className="subtle-copy">{headerCopy}</p>

        {isManagingOnBehalf ? (
          <label className="quick-event-field" style={{ maxWidth: 320 }}>
            <span className="quick-event-field-label">Client</span>
            <select
              value={selectedClientId}
              onChange={(e) => setSelectedClientId(Number(e.target.value))}
              disabled={availableClients.length === 0}
            >
              {availableClients.length === 0 ? <option value="">No clients available</option> : null}
              {availableClients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label || c.username}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <form className="entity-form-grid category-form" onSubmit={handleSubmit}>
          <label>
            Category name
            <input
              required
              value={formState.name}
              onChange={(e) => setFormState((current) => ({ ...current, name: e.target.value }))}
            />
          </label>

          <div className="entity-form-wide">
            <p className="menu-section-title">Preset Colors</p>
            <div className="color-picker-grid">
              {PRESET_CATEGORY_COLORS.map((color) => (
                <button
                  key={color.value}
                  className={formState.color === color.value ? "color-choice active" : "color-choice"}
                  onClick={() => setFormState((current) => ({ ...current, color: color.value }))}
                  style={{ "--category-color": color.hex }}
                  type="button"
                >
                  <span className="color-choice-swatch" />
                  {color.label}
                </button>
              ))}
            </div>
          </div>

          {errorMessage ? <p className="form-error entity-form-wide">{errorMessage}</p> : null}
          <div className="entity-form-actions entity-form-wide">
            <button className="task-create-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Saving..." : editingCategory ? "Save category" : "Create category"}
            </button>
            {editingCategory ? (
              <button
                aria-label="Close"
                className="entity-form-dismiss"
                onClick={() => {
                  setEditingCategory(null);
                  setFormState(getInitialFormState(null));
                }}
                type="button"
              >
                ×
              </button>
            ) : null}
          </div>
        </form>

        {listErrorMessage ? <p className="form-error">{listErrorMessage}</p> : null}
        {isLoadingCategories ? <p className="subtle-copy">Loading categories...</p> : null}
        <div className="category-list">
          {categories.map((category) => (
            <article key={category.id} className="category-item">
              <div className="category-item-main">
                <span className="category-swatch" style={{ background: getCategoryColorHex(category.color) }} />
                <div>
                  <strong>{category.name}</strong>
                  <p className="subtle-copy">{category.color}</p>
                </div>
              </div>
              <div className="category-item-actions">
                <button
                  className="calendar-nav-button"
                  onClick={() => {
                    setEditingCategory(category);
                    setFormState(getInitialFormState(category));
                  }}
                  type="button"
                >
                  Edit
                </button>
                <button className="entity-form-close" onClick={() => handleDelete(category.id)} type="button">
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
        <PaginationControls
          currentPage={currentPage}
          isLoading={isLoadingCategories}
          label="categories"
          onPageChange={loadCategories}
          totalPages={totalPages}
        />
      </section>
    </main>
  );
}
