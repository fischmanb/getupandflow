#!/usr/bin/env python3
"""Idempotent SEO enrichment for marketing/. Re-run after any page change.
- og:image on every page (site default if absent)
- BreadcrumbList JSON-LD derived from URL path + each page's <h1>
- WebSite node on the homepage
- sitemap.xml regenerated from the filesystem with lastmod from git history
"""
import glob, html, json, os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MK = os.path.join(ROOT, 'marketing')
SITE = 'https://getupandflow.co'
DEFAULT_OG = SITE + '/assets/logo-alt.png'
ORG_ID = SITE + '/#org'

def pages():
    out = []
    for f in sorted(glob.glob(os.path.join(MK, '**', 'index.html'), recursive=True)):
        rel = os.path.relpath(os.path.dirname(f), MK).replace(os.sep, '/')
        url = SITE + '/' + ('' if rel == '.' else rel)
        out.append((f, url, [] if rel == '.' else rel.split('/')))
    return out

def h1_of(text):
    m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
    assert m, 'no h1'
    return html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()

def inject_head(text, snippet):
    assert text.count('</head>') == 1
    return text.replace('</head>', snippet + '\n</head>', 1)

changed = []
h1s = {url: h1_of(open(f, encoding='utf-8').read()) for f, url, _ in pages()}
for f, url, segs in pages():
    s = open(f, encoding='utf-8').read(); orig = s
    if 'og:image' not in s:
        s = inject_head(s, f'<meta property="og:image" content="{DEFAULT_OG}">')
    if 'BreadcrumbList' not in s:
        items = [{'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE + '/'}]
        for i in range(1, len(segs) + 1):
            u = SITE + '/' + '/'.join(segs[:i])
            items.append({'@type': 'ListItem', 'position': i + 1, 'name': h1s[u], 'item': u})
        if len(items) > 1:
            ld = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': items}
            s = inject_head(s, '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + '</script>')
    if not segs and '"WebSite"' not in s:
        ld = {'@context': 'https://schema.org', '@type': 'WebSite', '@id': SITE + '/#website', 'url': SITE,
              'name': 'Get Up and Flow', 'publisher': {'@id': ORG_ID}, 'inLanguage': 'en-US'}
        s = inject_head(s, '<script type="application/ld+json">' + json.dumps(ld) + '</script>')
    if s != orig:
        open(f, 'w', encoding='utf-8').write(s); changed.append(url)

# sitemap from filesystem + git lastmod (falls back to today's date for uncommitted files)
def lastmod(f):
    out = subprocess.run(['git', 'log', '-1', '--format=%cs', '--', f], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return out or subprocess.run(['date', '+%Y-%m-%d'], capture_output=True, text=True).stdout.strip()
entries = ''.join(f'  <url><loc>{url}</loc><lastmod>{lastmod(f)}</lastmod></url>\n' for f, url, _ in pages())
sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + entries + '</urlset>\n'
smp = os.path.join(MK, 'sitemap.xml')
if open(smp).read() != sm:
    open(smp, 'w').write(sm); changed.append('sitemap.xml')
print('pages:', len(pages()), 'changed:', changed)
