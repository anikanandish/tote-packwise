# Packing Simulator website

A standalone website that shows how the `packer.cpp` algorithm packs a TOTE order, and compares it with packing without the algorithm.

- `index.html` is the site. Open it through a local web server (below).
- `page.html` + `builtin-data.json` are the sources; `build.py` rebuilds `index.html` from them.
- `vendor/three.min.js` is Three.js r128 (MIT, see `vendor/three-LICENSE.txt`) for the 3D view.
- `tests/equivalence.mjs` proves the JavaScript port matches the original program.

## Run (Windows)

```bat
cd /d "C:\Users\renuk\OneDrive\Desktop\TOTE-PACKWISE\tote-packwise\simulator-site"
py -m http.server 5175
```

Open http://localhost:5175. Start the API (port 8000) first if you want live store orders; otherwise the site uses its built-in copy of the catalogue and says so at the top. To use an API on another address: `http://localhost:5175/?api=http://127.0.0.1:8000`.
