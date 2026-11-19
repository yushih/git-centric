# Repository landing page

Serve a read-only repository overview at the root. Load repo.get on mount,
show branch, commit and collaboration status, and provide refresh and retry.
Verify the production frontend and exercise the served page against a local repo.

Implemented the initial visible shell in main.tsx and style.css. The production
build passed and all five frontend RPC tests passed. Built a wheel and installed
it in a temporary environment with existing runtime dependencies, exercised
gc web --help and verified the bundled index references the overview JavaScript.
Setup actions and navigation to feature screens remain subsequent work.
