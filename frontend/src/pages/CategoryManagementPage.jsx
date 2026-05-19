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
  const { selectedClients, supportsClientFiltering } = useClientFilter();

  const [categories, setCategories] = useState([]);
  const [editingCategory, setEditingCategory] = useState(null);
  const [formState, setFormState] = useState(getInitialFormState(null));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingCategories, setIsLoadingCategories] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [listErrorMessage, setListErrorMessage] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);

  // The "active client" is whatever the hamburger menu has selected.
  // Clients are themselves. Coaches/Admins inherit from the filter, but only
  // when exactly one client is selected (multiple ambiguous, none impossible).
  const activeClient = useMemo(() => {
    if (!supportsClientFiltering) return { id: user?.id, label: "" };
    if (selectedClients.length === 1) return selectedClients[0];
    return null;
  }, [selectedClients, supportsClientFiltering, user?.id]);

  async function loadCategories(page = currentPage) {
    if (!activeClient) {
      setCategories([]);
      setTotalPages(0);
      setIsLoadingCategories(false);
      return;
    }
    setIsLoadingCategories(true);
    setListErrorMessage("");
    try {
      const params = { page };
      if (supportsClientFiltering) params.client_id = activeClient.id;
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

  useEffect(() => {
    loadCategories(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeClient?.id]);

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");

    if (!activeClient) {
      setErrorMessage("Pick a single client in the menu before managing categories.");
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = { ...formState };
      if (supportsClientFiltering) payload.client_id = activeClient.id;

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
    if (!window.confirm("Delete this category? Events using it must be re-categorized first.")) return;
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

  return (
    <main className="content-page">
      <section className="content-card">
        <Link className="back-link" to="/app">← Back</Link>
        <p className="eyebrow">Event Categories</p>
        <h2>Manage event categories</h2>
        <p className="subtle-copy">
          Categories are only used for events and must use one of the preset colors.
        </p>

        {!activeClient && supportsClientFiltering ? (
          <p className="form-error">
            Select a single client from the menu to manage their categories.
          </p>
        ) : null}

        {activeClient ? (
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
        ) : null}

        {listErrorMessage ? <p className="form-error">{listErrorMessage}</p> : null}
        {isLoadingCategories ? <p className="subtle-copy">Loading categories...</p> : null}
        <div className="category-list">
          {categories.map((category) => (
            <article key={category.id} className="category-item">
              <div className="category-item-main">
                <span
                  className="category-swatch"
                  style={{ background: getCategoryColorHex(category.color) }}
                />
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
                <button
                  className="entity-form-close"
                  onClick={() => handleDelete(category.id)}
                  type="button"
                >
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
