# Get Up and Flow — Planner

Daily calendar + tasks app for GUAF clients and the offshore coaches who work with them. Coaches see exactly what the client sees, switching between clients via a hidden menu so the screen-share experience matches the client's own view.

- **Backend**: Django 5 + DRF + SimpleJWT (5-min access, 1-day refresh, rotating). Three roles via Django Groups: `Admin`, `Coach`, `Client`.
- **Frontend**: React 18 + Vite + React Router. Axios with token-refresh interceptor.
- **DB**: Postgres in prod, SQLite for local dev.
- **Hosting**: Render (backend), Vercel (frontend), Supabase (Postgres).

---

## Local development

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DJANGO_DEBUG=True
export DJANGO_SECRET_KEY=dev-only
export DATABASE_URL=sqlite:///dev.sqlite3

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Backend serves on `http://127.0.0.1:8000`.
- Swagger UI: `/api/docs/swagger/`
- Django admin: `/admin/` — use this to create Coach and Client users and set `profile.assigned_coach` for each Client. The `Admin`/`Coach`/`Client` groups auto-create on first `migrate`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend serves on `http://localhost:5173`. API base URL auto-detects to `http://127.0.0.1:8000/api` in dev. To override, create `frontend/.env.local`:

```
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

### Tests

```bash
cd backend
python manage.py test
```

---

## Production deployment

The architecture: `app.getupandflow.co` (Vercel) calls `api.getupandflow.co` (Render). Landing at `www.getupandflow.co` is unchanged (Base44).

### Backend — Render

1. New Web Service from this repo, root directory `backend`, runtime Docker. Render auto-detects the `Dockerfile`.
2. Set environment variables in the Render dashboard:

   | Variable | Value |
   |---|---|
   | `DJANGO_SECRET_KEY` | new long random string |
   | `DJANGO_DEBUG` | `False` |
   | `DJANGO_ALLOWED_HOSTS` | `api.getupandflow.co,<service>.onrender.com` |
   | `CORS_ALLOWED_ORIGINS` | `https://app.getupandflow.co` |
   | `CSRF_TRUSTED_ORIGINS` | `https://app.getupandflow.co` |
   | `DATABASE_URL` | Supabase Postgres connection string |
   | `DJANGO_SECURE_SSL_REDIRECT` | `True` |
   | `WEB_CONCURRENCY` | `2` |

3. Render → Settings → Custom Domains → add `api.getupandflow.co`. Render gives a CNAME target.
4. At GoDaddy DNS: add CNAME `api` → `<Render's CNAME target>`. SSL provisions automatically.

### Frontend — Vercel

1. New Vercel project from this repo, root directory `frontend`, framework preset Vite.
2. Set environment variable: `VITE_API_BASE_URL=https://api.getupandflow.co/api`
3. Vercel → Settings → Domains → add `app.getupandflow.co`.
4. At GoDaddy DNS: add CNAME `app` → `cname.vercel-dns.com`.

The included `frontend/vercel.json` already handles SPA fallback routing.

---

## Domain models (quick reference)

- `UserProfile` — each Client has exactly one `assigned_coach`. Validated at save time.
- `EventCategory` — per-Client, with 6 preset colors. Used on Events only.
- `Event` — title, date, start/end time, location, description, category, recurrence (`none`/`daily`/`weekly`/`monthly` with end date).
- `Task` — title, deadline, description, `completed_at` nullable.

RBAC is enforced at the queryset layer via `RoleScopedQuerysetMixin` in `backend/planner/views.py`. Admins see all; Coaches see only events/tasks where `client.profile.assigned_coach == self`; Clients see only their own. The `?client_ids=` query param filters within that RBAC scope — it cannot be used to escape it.

## Repo layout

```
backend/         Django project
  accounts/      Users, roles, profiles, auth views
  planner/       Events, tasks, categories, analytics
  config/        Django settings, URL conf
frontend/        React + Vite SPA
  src/
    api/         Axios client + token refresh
    auth/        Auth context + token storage
    calendar/    Calendar view utilities + state
    components/  UI components (CalendarPanel, TaskPanel, etc.)
    filters/     Client filter context (multi-select)
    pages/       Route-level pages (Login, Home, Admin, etc.)
```
