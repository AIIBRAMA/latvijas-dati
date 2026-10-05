# USAspending code provenance

Source: https://github.com/fedspendingtransparency/usaspending-website
Branch inspected: master
Commit: 86af01ba9ab403f2ed75f1d62a0dbcd35dbc4076
Retrieved: 2026-10-05
License: CC0 (see root LICENSE.md)

Original source paths for the included reference files:
- components/TreemapCell.jsx → src/js/components/sharedComponents/TreemapCell.jsx
- components/ExplorerTreemap.jsx → src/js/components/explorer/detail/visualization/treemap/ExplorerTreemap.jsx
- components/colorHelper.js → src/js/helpers/colorHelper.js

The runnable Latvian adaptation is under lv/src/. TreemapCell retains the original
component with local imports, keyboard interaction, accessible labels, highlight
contrast and colors modified. colorHelper is retained unchanged. CategoryMap
adapts ExplorerTreemap's D3 hierarchy, binary treemap and cell composition to
Latvian dataset counts and responsive width, without the U.S. spending model.

The reference README and manifest document the original application. They are
not the installation instructions or dependency manifest for the Latvian app.
