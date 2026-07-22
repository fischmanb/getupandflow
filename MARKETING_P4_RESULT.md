# Marketing P4 Result — Static marketing site + leads backend

Branch: `marketing-p4` (off `main` @ 7b4b42b). Not pushed, per instructions.

## What was built

### `marketing/` — static site (replaces Base44)

Plain HTML + built Tailwind CSS. **Not Astro** — judgment call: this is a single
page with verbatim copy and zero templating/content-collection needs. Astro would
add a build pipeline, a dependency tree, and an indirection layer to produce the
same single HTML file. Plain HTML *is* the deliverable format the GEO goal asks
for; there is nothing for Astro to earn its keep on. If the site grows to multiple
pages (FAQ, blog), revisit.

Files:

| File | Purpose |
|---|---|
| `index.html` | The entire page, all copy server-rendered (verbatim from spec) |
| `assets/site.css` | Built Tailwind (v4, minified, ~33 KB) — **committed**, so Vercel needs no build step |
| `src/input.css` | Tailwind source (`@import "tailwindcss"` + ticker keyframes + reduced-motion opt-out) |
| `assets/logo.png`, `assets/logo-alt.png`, `assets/whoweare.png` | Downloaded from Supabase and self-hosted — no Base44/Supabase dependency remains |
| `js/main.js` | Progressive enhancement only: founder-video bubble/modal + lead form fetch |
| `vercel.json` | `cleanUrls`, `/faq` → `/` 302, immutable cache headers for `/assets/*` |
| `robots.txt` | Allow all, explicit stanzas for GPTBot, ClaudeBot, Claude-Web, PerplexityBot, Google-Extended; sitemap pointer |
| `sitemap.xml` | Single URL |
| `package.json` | Dev-only: `npm run build` = Tailwind CLI (`@tailwindcss/cli`) |

Page structure is exactly the 7 sections from the spec (hero + ticker, how it
works, why it works + testimonial, who we are, pricing, signup, footer), all copy
verbatim. Design matched to the live site: slate palette, blue-600→emerald-500
gradients, rounded-2xl cards, py-24/32 sections, system-UI font stack (verified
against the live CSS bundle — it ships Tailwind's default `ui-sans-serif` stack,
no webfont).

Ticker: pure CSS — duplicated list inside `w-max` flex, `translateX(-50%)` over
45s linear infinite, edge-fade mask, paused under `prefers-reduced-motion`.

Founder video (Vimeo 1133967200): floating circular bubble bottom-left with
"👋 Hear from our founder" pill and dismiss X. The looping background preview
iframe is injected by JS *after* `load` so the Vimeo embed never blocks first
paint (Lighthouse); without JS the bubble shows a play button. Clicking the
bubble — or the play overlay on the who-we-are photo — opens a modal with the
full player (`src` set on open, cleared on close; Escape/backdrop close). The
modal iframe idles at `about:blank` until opened, so no Vimeo request happens
unless a user asks for the video.

Signup form: real radios/inputs (plan, billing period, name, email, notes) styled
with peer-checked classes — the form is fully rendered and readable with JS
disabled. `js/main.js` submits JSON via fetch to
`https://api.getupandflow.co/api/leads/` with success / validation-error / 429 /
network-failure messages in an `aria-live` status line.

GEO layer:
- One `h1`; semantic `<header>/<main>/<section>/<article>/<figure>/<footer>`; `aria-labelledby` on sections.
- Meta description exactly as specified; OG/Twitter tags mirror the live site's (verified by fetching the live page), except `og:image` now points at the self-hosted `assets/logo-alt.png`.
- Canonical `https://getupandflow.co`.
- JSON-LD: `Organization` (name, url, email, logo) + `Service` (serviceType "Executive function coaching", provider ref, two Offers at 750/200 USD with the plan one-liners). Nothing invented — no ratings, no fake review markup.
- Alt text on every image, `loading="lazy"` on the below-fold photo, width/height attrs to prevent CLS, zero console errors (verified headless).

### `backend/leads/` — real form backend

New Django app matching the existing app structure (`apps.py`/`models.py`/
`serializers.py`/`views.py`/`urls.py`/`admin.py`/`tests.py`):

- **Model** `Lead`: `full_name`, `email`, `plan` (full_support/focus_lite), `billing_period` (monthly/weekly), `notes` (blank ok), `created_at`; ordered newest-first.
- **Endpoint** `POST /api/leads/` — `CreateAPIView`, `AllowAny`, no auth classes, `ScopedRateThrottle` scope `leads` at **10/hour per IP** (overridable via `LEADS_THROTTLE_RATE` env var).
- **Admin**: list of name/email/plan/billing/created, filters + search.
- **Migration**: `leads/0001_initial.py` (makemigrations only, not applied to any repo DB).
- **CORS**: `https://getupandflow.co` + `https://www.getupandflow.co` are appended to `CORS_ALLOWED_ORIGINS` in settings *after* the env read, so a production `CORS_ALLOWED_ORIGINS` env override can't accidentally drop the marketing origins. (django-cors-headers is global-middleware, not per-endpoint; the leads endpoint is the only `AllowAny` POST, and the marketing origins gain nothing on the other endpoints since those all require JWT auth.)

## Test output

Full suite (includes 9 new leads tests: create, optional notes, email/name/plan
validation, GET 405, throttle 429, CORS headers for both marketing origins):

```
Found 82 test(s).
System check identified no issues (0 silenced).
OK
```

`manage.py makemigrations --check --dry-run` → `No changes detected` (clean).

App frontend `npm run build` (vite) → `✓ built in 819ms`, unaffected.

Live verification performed locally:
- Served `marketing/` and screenshotted at 1440px and 390px (real mobile viewport via devtools protocol): all sections render, no horizontal overflow (`scrollWidth == clientWidth == 390`), zero console errors.
- Ran the backend against a throwaway sqlite DB and exercised the endpoint with `Origin: https://getupandflow.co`: preflight OPTIONS returns the origin + POST in allow-methods; POST returns 201 with the ACAO header; bad payload returns 400.

## Vercel project + domain cutover

1. **Create the project**: Vercel dashboard → Add New Project → import this repo → set **Root Directory = `marketing/`**, Framework Preset = **Other**, Build Command = *(empty)*, Output Directory = `.` (the built CSS is committed, so deploys are pure static). Alternatively: `cd marketing && vercel --prod`.
2. **Verify the preview URL**: page renders, `/faq` 302s to `/`, `/robots.txt` + `/sitemap.xml` serve.
3. **Backend first**: deploy the `marketing-p4` backend (run `manage.py migrate` on Koyeb) so `api.getupandflow.co/api/leads/` exists *before* the marketing cutover — otherwise the form errors.
4. **Domain cutover**: in the *old* Base44/current project, remove the `getupandflow.co` + `www.getupandflow.co` domains; add both to the new marketing project (Settings → Domains). Set `www` → redirect to apex (or vice versa, matching current setup). DNS already points at Vercel, so this is instant; no registrar changes needed unless the domain is currently pointed at Base44's infrastructure directly — in that case set apex A → `76.76.21.21` and `www` CNAME → `cname.vercel-dns.com`.
5. **Smoke test on the real domain**: submit the form once (it will appear in Django admin under Leads), confirm `curl -s https://getupandflow.co | grep "not lazy"` returns the hero copy with no JS.

## Judgment calls

- **Plain HTML over Astro** — see rationale above.
- **Built CSS committed** so the Vercel project needs no build step and no node toolchain; regenerate with `cd marketing && npm install && npm run build` when editing classes.
- **Header on small phones** shows only the logo mark (name appears ≥480px) — the full brand + Log in + CTA doesn't fit 390px without wrapping.
- **Pricing-card Monthly/Weekly toggle is static** (Monthly highlighted), as specced ("static default Monthly"); no weekly price was given anywhere, so no JS price-swapping was invented. The *signup form's* toggle is a real radio group and posts `billing_period` to the API.
- **Bubble video injected post-load** rather than a hardcoded autoplay iframe — keeps first paint clean and Lighthouse happy while still being "a Vimeo iframe" per spec; degrades to a play button without JS.
- **Throttle 10/hour/IP** with `LEADS_THROTTLE_RATE` env escape hatch — tight enough to blunt spam, loose enough for a shared office IP.
- **`Claude-Web` added to robots.txt** alongside the four specified crawlers (it's Anthropic's other UA); harmless and consistent with intent.
- **og:image** points at the self-hosted square logo rather than the Supabase render URL — removes the last Base44-era dependency; consider a purpose-made 1200×630 card later.
