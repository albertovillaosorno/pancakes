# PDF

This folder is the Pancakes Media PDF delivery boundary.

Executable PDF code lives under `src/pancakes_media/pdf/`. Generated PDF artifacts belong under ignored `pdf/data/` paths only when an explicit delivery task approves the input package.

PDF rendering consumes validated Pancakes report JSON and delegates generic PDF writing to `libraries/pdf`.
