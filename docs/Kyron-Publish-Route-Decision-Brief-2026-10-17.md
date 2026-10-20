# Kyron region-pack publish route — decision brief (Oct 17, 2026)

## The blocker, precisely

Four packs are staged and audited in `~/kyron-build/fl-publish/`:
FL 7.90 MB · GA 33.67 MB · TN 18.42 MB · SC 8.42 MB (total ~68.4 MB).
Nothing is published: the app's manifest URLs point at GitHub Pages
(e.g. `https://markbentzjr.github.io/kyron/data/us-fl.manifest.json`, pack
resolved relative to the manifest) and both the manifest and pack URLs
return 404. The GitHub connector cannot carry the packs (~90 KB per-call
cap, no release-asset upload), and the browser web-upload route caps at
25 MB per file — which GA alone exceeds.

## Verified platform limits (checked Oct 17, 2026)

- GitHub web upload: 25 MB per file. Git push: warning over 50 MB,
  hard block over 100 MB per file.
- GitHub Pages (official docs): published site max 1 GB, source repo
  recommended max 1 GB, soft bandwidth 100 GB/month.
  https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- GitHub Releases (official docs): each asset must be under 2 GiB, up to
  1,000 assets per release, **no limit on total release size or bandwidth**.
  https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases

## The two real routes

**Route A — Pages via git push (no app change).**
All four packs are under git's 100 MB hard limit, and ~68 MB total is far
under the Pages 1 GB site cap, so Pages itself is NOT the problem — only
the browser-upload route is. Publishing works the moment a git-capable
push (e.g. from Mark's Mac, or any authenticated git client) pushes
pack-first, manifest-last to `data/` on the Pages branch. FL goes live in
the already-shipped app with zero app changes. Weakness: every future
state pack adds to the 1 GB Pages site and the 100 GB/month soft
bandwidth; a large state (e.g. a future TX/CA-scale pack) or real download
volume will eventually force a migration anyway.

**Route B — GitHub Releases assets (needs the next build).**
Move packs to Release assets and repoint each region's manifestUrl.
Releases have no bandwidth cap and a 2 GiB per-asset limit, so this route
never needs to be revisited. Cost: it is an app change — but the next
build already has to happen to register TN and SC (FIX5 registers only
us-al/us-fl/us-ga), so the repoint rides that same vc10 build at near-zero
marginal cost. FL/GA would wait for that build instead of going live
immediately.

## Recommendation (CSDM)

Do both, in this order:
1. **Now:** Route A for FL only — FL is registered in the shipped app,
   fits every limit, and users get a second state immediately. Publish
   pack first, manifest last; do NOT publish GA/TN/SC manifests until
   their packs and registrations are live (a manifest without a pack, or
   a pack for an unregistered region, is a broken offer in Coverage).
2. **In the vc10 build** (TN+SC registration batch): switch all regions
   to Route B (Releases) so GA's 33.67 MB and all future states publish
   through one permanent route, then publish GA+TN+SC together.

This keeps the "packs first, manifests last" rule, invents no new host,
costs $0, and respects the free/local-first policy — packs remain static
files, no backend, no keys in the app.

## What Mark actually has to decide

Only step 1 needs a human with git access to markbentzjr/kyron: a single
push of `us-fl-2026-10-15.1.db.gz` (7,900,234 bytes, sha256
2c47c3d53f0446e9330c9bb3af457fe1a8d9c8d4cee2f527d6ebe6c264523b8d) followed
by `us-fl.manifest.json` to `data/`. Everything else is build-team work.
