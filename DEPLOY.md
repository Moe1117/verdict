# Deploying the static demo

The web UI is a static Vite SPA. The frozen examples — the Methods Verifier demo + the 594-line
benchmark, the trial deck, and the evidence cards — are bundled JSON, so the **hosted build works with
no backend**: a reviewer opens the URL and sees the full demo and the real numbers. The live
"Verify / Review / Resolve" buttons need the API (`uvicorn verdict.webapp:app --port 8010`); the hosted
build detects its absence and shows the saved examples with a one-line note.

## Build
    cd web && npm install && npm run build      # -> web/dist (fully static)

## Deploy (pick one)
- **Netlify** — connect the repo; `netlify.toml` sets base=web, publish=dist. Or CLI:
      cd web && npm run build && npx netlify deploy --prod --dir dist
- **Vercel** — `cd web && npx vercel --prod`  (auto-detects Vite; builds + deploys)
- **GitHub Pages / any static host** — serve `web/dist` at the domain **root** (the app fetches assets
  from absolute paths like `/repro/benchmark.json`, so host at root, not a subpath).

## Preview the static build locally, exactly as a judge sees it (no backend)
    cd web && npm run build && python3 -m http.server 4173 --directory dist
    # open http://localhost:4173 — frozen demo + benchmark render; live buttons show the static note.
