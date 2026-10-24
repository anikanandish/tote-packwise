# TOTE + PackWise

**TOTE** is an online shop. **PackWise** is the warehouse app that packs TOTE orders in the smallest carton that keeps them safe, using your existing C++ packing algorithm, and reports the packaging cost saved.

```
 TOTE store (React, :5173) ─┐                       ┌─ SQLite (backend/data/tote_packwise.db)
                            ├─► FastAPI (:8000) ────┤
 PackWise   (React, :5174) ─┘     │  HTTP + JSON    └─ C++ packing service (:8090)
                                  └────────────────────►  original pack() algorithm
```

Four separate programs: two React + Vite frontends (the PackWise one also contains the **admin console**), one FastAPI backend, one C++ HTTP microservice. A fifth, optional, static simulator website runs on port 5175.

---

## 1. What your `packer.cpp` does (inspected first)

> PackWise now packs with the **cushion optimizer (optimizer2)** and 16 cartons by default; see below. This section describes the original algorithm, still available with `PACKING_ALGORITHM=original`.

| Question | Answer from the source |
|---|---|
| Input | `n`, then `n` lines of integer `l w h` on stdin |
| Output | Designed box `W L H`, then `id x y z l w h rotated` per item |
| Method | Sort items by longest floor side; for 200 candidate widths, place items in **rows** (shelf heuristic); keep the width with the lowest score = box volume + 0.025 × (largest side)² |
| 2D or 3D? | **Single-layer**: every `z` is 0. Heights only set the box height. No stacking. |
| Rotation | 90° in the floor plane only (swaps `l` and `w`). Items are never tipped. |
| Fixed cartons | No. It designs a box; it cannot test a given carton. |
| Weight, padding, fragility, inventory | None. |

**How it is integrated (and what was added):** the original `pack()` is copied verbatim into `cpp-packer-service/src/packer_core.cpp`, and the original `main()` sweep lives on as `design()`. The only extension is `fitCarton()`, which runs the original width search inside one fixed carton: the original `pack()` at 200 row widths up to the carton's floor side (both orientations), keeping the lowest-scoring layout that fits the other floor side and the height. Everything the algorithm does not know — padding, weight, fragile protection, stock, cost — is done by the FastAPI feasibility layer. Details: [`cpp-packer-service/README.md`](cpp-packer-service/README.md).

The UI says this plainly: plans are drawn as a single layer, and nothing is ever shown stacked.

### The cushion optimizer (`optimizer2.cpp`) — the default

`cpp-packer-service/original/optimizer2.cpp` is the original `packer.cpp` row heuristic plus a fixed **15 mm** cushion per dimension (7.5 mm on every side) for fragile items. One layer, no stacking, 90° floor rotation only. `pack()` and the 200-width search are copied verbatim into `src/optimizer2_core.cpp` (`design()` matches the compiled original on 500 random inputs); `optimizer2::fitCarton()` runs that search inside each warehouse carton. Fragile items are sent without padding (`fragile: true`); other items keep their product padding. Smallest carton that fits wins.

**16 standard cartons.** STD-09 to STD-16 were added to fill the size gaps of the first eight (mostly height): Tall Bottle Mailer 150×100×150, Flat Book Mailer 250×180×50, Tall Cosmetics Box 200×150×150, Document / Flat Gift Box 320×240×60, Cube Gift Box 200×200×200, Tall Vase / Diffuser Box 120×120×250, Medium Tall Box 300×200×200, Large Flat Box 400×300×100 (mm, nominal, not measured; sample stock and prices like the first eight). They are added automatically to an existing database on the next start.

Switch algorithm in `backend\.env`: `PACKING_ALGORITHM=optimizer2` (default), `optimizer` (layered, below) or `original`.

**Made-to-measure box, edge cases only.** With `optimizer2`, the backend also asks the engine for the box the algorithm designs itself (`/v1/pack/design` with `"algorithm": "optimizer2"`). If no stock carton fits, or the smallest stock carton that fits is more than `CUSTOM_BOX_WHEN_STOCK_OVER` (default **1.5**) times that volume, the order gets a **Made-to-measure box** (`MTM-BOX`) cut to the design; otherwise the stock carton is used. Its price is the board-area estimate (sample). `CUSTOM_BOX_WHEN_STOCK_OVER=0` turns it off.

### The layered optimizer (`optimizer.cpp`)

| Question | Answer from the source (`cpp-packer-service/original/optimizer.cpp`) |
|---|---|
| Input | `n`, then `n` lines of `l w h [fragile 0/1]` |
| Method | Sort items by footprint area (largest first). Try 60 widths spaced geometrically; for each, binary-search the shortest length. `pack3D()` fills **rows**, then **layers**, then stacks layers (max 300 mm). Lowest score = volume + 0.025 × (largest side)² wins (box sides below 180 × 100 × 50 mm count as that size). |
| 3D? | **Yes**: items are stacked in layers (`z` can be above 0). |
| Fragile | A fixed **30 mm** cushion per dimension (15 mm on every side). |
| Rotation | 90° in the floor plane only. Items are never tipped. |

**How it is integrated:** `pack3D()` and the search are copied verbatim into `cpp-packer-service/src/optimizer_core.cpp` (`optimizeDesign()` is the program's `main()` and was checked against the compiled original on 400 random inputs: identical output). The only addition is `optimizer::fitCarton()`, which runs the same search limited to one warehouse carton (widths up to the carton side, length up to the other side, stack height up to the carton height), both floor orientations, lowest score kept. The backend still picks the **smallest** carton that fits. Fragile items are sent to the engine without padding and `fragile: true`, so the optimizer adds its own cushion; other items keep their product padding.

**Switch back to the old algorithm** (no code change): add `PACKING_ALGORITHM=original` to `backend\.env` and restart the API. `PACKING_ALGORITHM=optimizer` (or no line) uses the new one. The simulator website and the in-app simulator still show the original `packer.cpp`.

---

### The eight standard cartons (millimetres)

PackWise packs into the eight standard carton sizes below. Admins can add their own cartons.

| Code | Name | Nominal L × W × H (mm) | Volume |
|---|---|---|---|
| STD-01 | Ultra-Small / Cosmetics | 100 × 100 × 50 | 0.50 L |
| STD-02 | Small Mailer / Accessories | 200 × 150 × 100 | 3.00 L |
| STD-03 | Medium Mailer / Skincare Kit | 230 × 150 × 100 | 3.45 L |
| STD-04 | Standard E-commerce Box | 300 × 230 × 100 | 6.90 L |
| STD-05 | Shoe Box / Small Gadgets | 300 × 200 × 130 | 7.80 L |
| STD-06 | Medium Apparel / Electronics | 360 × 250 × 150 | 13.50 L |
| STD-07 | Large Multi-Item Box | 460 × 360 × 200 | 33.12 L (baseline for savings) |
| STD-08 | Heavy Gadget Carrier | 290 × 280 × 130 | 10.56 L |

STD-01 to STD-04 are e-commerce and retail small mailers. STD-05 to STD-08 are consumer-goods and electronics shipping boxes.

**What is stored and what is not invented:**
* **Sizes are stored in whole millimetres.** Every carton has a **nominal** size (the size above) and an **internal** size. Fitting always uses the internal size.
* **Internal size:** until someone measures a real carton, the internal size equals the nominal size and is marked **Not verified**. Plans then carry the warning "nominal size used for fitting". Record the measured inside size on the Cartons page and tick *verified*.
* **Maximum weight is not set:** no verified figure exists. While it is empty, the weight check shows as *not checked* rather than passing silently.
* **Stock (40 each) and prices are sample values.** Prices come from the board-area rule `(2L + 2W + 3.5 cm) × (H + W) × BOARD_COST_PER_M2 + BOX_MAKE_COST`. They are tagged **sample** everywhere they appear, including reports. The tag disappears for a field once an admin enters a real value. To start with zero stock and no prices instead, set `SEED_SAMPLE_CARTON_VALUES=false`.
* **Seeding is idempotent:** cartons are only added if their code is missing, so restarts never duplicate them or reset admin edits and stock.
* **Upgrading an older database:** the API migrates the `cartons` table from centimetres to millimetres. Row ids are kept, so all history stays linked. It then switches off the old cartons (`CTN-*`, `BOX-*`) once and adds the eight standard ones. Retired cartons are hidden on the Cartons page unless you tick *Show retired cartons*.

**How a carton is chosen for an order (unchanged algorithm):**
1. Every unit is padded (fragile items get at least 1 cm) and rounded up to whole mm.
2. Each active carton is checked: every item upright under the internal height, footprint, weight (when set), stock and materials.
3. For each remaining carton the C++ engine runs the original width search with the unchanged `pack()`: 200 row widths up to the carton side, in both floor orientations. It keeps the tightest layout that fits.
4. **The smallest carton (by internal volume) that passes everything wins.** Equal volumes go to the cheaper carton.

The demo order (lipstick, nail-polish remover, 2 eyeliners, perfume) gets **STD-06 Medium Apparel / Electronics**. The padded perfume and remover are 140 mm tall and stay upright, and only STD-06 (150 mm) and STD-07 (200 mm) are tall enough. A single lipstick gets **STD-02**. The Cedar Reed Diffuser (240 mm with padding) fits **no** standard carton. PackWise says so and suggests adding a carton at least 240 mm tall.

### Admin console (PackWise → `/admin`)

A separate area of the PackWise app, at http://localhost:5174/admin/login. It is not part of the customer shop.

* **Sign-in:** opened with the **admin access code** (`ADMIN_ACCESS_CODE` in `backend\.env`). The code is checked only by the server (constant-time compare). It is never sent to the browser, returned by the API or written to logs.
* **Sessions:** the server returns a session token, and only its SHA-256 hash is stored. Every `/api/admin/*` endpoint checks for an admin session, so a customer or worker token gets `403`, and no token gets `401`.
* **Wrong codes:** after 5 wrong codes from one computer, sign-in pauses for 5 minutes.
* **Sign out** is in the sidebar, with a confirmation.
* **Scope:** this is demo-level access control, not production identity management.

**Sections:**

| Section | What it does |
|---|---|
| **Overview** | Order counts, orders awaiting packing, packaging cost by day, savings vs baseline, carton stock bars with low-stock markers, carton data still to confirm, efficiency (utilisation, volume avoided, empty space), no-fit orders, overrides, recent activity. |
| **Orders** | Every TOTE order with its current packing result. Filter by code, customer, status, packing result (not planned / no fit / override), carton and date. |
| **Order detail** | Items with packaging data, timeline, completion record, overrides, and every packing plan. For each plan: the selected carton, warnings, *why this carton*, a 3D / top-view blueprint drawn from the stored engine coordinates, the coordinate table (mm, straight from the engine JSON), the worker's packing instructions, all candidate cartons with each check, the padded items sent to the engine, and the raw engine request and response. A no-fit plan shows the reasons and what could be done. |
| **Packing results** | Every plan ever made (including superseded, cancelled, no-fit), filterable; opens the order detail at that plan. |
| **Cartons** | The eight standard cartons and custom ones: nominal and internal sizes (mm), verified flag, volume (calculated), max weight, cost, stock and threshold, usage. Search, filter, sort; add, edit, adjust stock, view stock history. Activate and deactivate need a confirmation. Deactivating is refused while cartons are reserved for packing in progress, or for the baseline. Only custom cartons that never appeared in a plan can be deleted; standard cartons can only be deactivated. |
| **Products** | Add and edit products: price, stock, on sale, size, weight, fragile, padding, orientation, protective material. Shows the packed size the engine will receive. |
| **Protective materials** | Stock, cost and thresholds for bubble wrap, kraft paper and so on. |
| **Reports & sustainability** | Packed orders filtered by date, carton and order code. Cost, savings vs baseline, carton usage, volume shipped, volume avoided vs baseline (calculated), empty space and cardboard area (estimates), materials used, CSV export, and the calculation method. Rows that used a sample carton price are tagged. |
| **Settings** | Engine status and capabilities, packing rules, baseline carton, and whether the worker and admin codes are configured (never their values). |

### Algorithm simulator (PackWise → Algorithm simulator)

Runs your original algorithm on real TOTE orders (or any mix of catalogue products) and shows:
1. **Width search**: all 200 row widths it tries, the box each produces, and the one it keeps.
2. **Placement, step by step**: play, pause and step through the items in the algorithm's order (top view or 3D), with what happened at each step (new row, turned 90°).
3. **With vs without the algorithm**: the algorithm's box against two ways of packing without it, *one straight row* (side by side in pick order, no turning, no width search) and *the smallest stock carton* that safely fits. All three are drawn to the same scale, with volume, fill, empty space, cardboard, cost and void-fill paper.
4. **Across recent website orders**: the same comparison totalled over the latest orders.

API (staff sign-in): `GET /api/sim/orders`, `GET /api/sim/orders/{id}`, `POST /api/sim/custom`, `GET /api/sim/summary`, `GET /api/sim/products`.
Engine: `POST /v1/pack/sweep` runs the same loop as the original `main()` and records every trial; its chosen box and placements match the original program (checked on 300 random orders, plus an automated test).

### Packing Simulator website (`simulator-site\`, port 5175)

A separate website just for the simulation. It does not call the C++ engine: `pack()` and the 200-width search from `packer.cpp` are ported line for line to JavaScript, so the whole simulation runs in the browser. `simulator-site\tests\equivalence.mjs` compiles the original `packer.cpp`, runs both on random baskets and requires identical boxes and coordinates (600 of 600 identical).

- **Data from the store:** when the API is running, the site reads products, cartons, packing rules and recent orders from `GET /api/public/sim-data` (no sign-in, no customer details). If the API is off it uses a built-in copy of the TOTE catalogue and says so at the top.
- **Sections:** choose a basket (store order, sample basket or build your own) → the width search (chart of all 200 trials; drag through any trial to see its layout) → placement step by step (top view or 3D) → with vs without the algorithm (same scale, metrics table, savings).
- Plain HTML, no `npm install`. Start it with `py -m http.server 5175` inside `simulator-site`.

## 2. Install the prerequisites (Windows 11)

| Tool | Version | Get it |
|---|---|---|
| Python | 3.11 or 3.12 | python.org — tick **"Add python.exe to PATH"** |
| Node.js | 20 LTS or newer | nodejs.org |
| C++ compiler (optional at first) | MinGW-w64 g++ 12+ | see below |

**Install a C++ compiler (MSYS2):**

1. Install MSYS2 from msys2.org.
2. Open **MSYS2 UCRT64** and run: `pacman -S --needed mingw-w64-ucrt-x86_64-gcc`
3. Add `C:\msys64\ucrt64\bin` to your Windows PATH, then open a new Command Prompt and check `g++ --version`.

No compiler yet? Setup falls back to `cpp-packer-service\prebuilt\packer_service.exe`, built from the same source.

## 3. Set up (once)

Open **Command Prompt** in the `tote-packwise` folder:

```bat
setup.bat
```

It copies the `.env.example` files to `.env`, creates the Python virtual environment, installs packages for both frontends, and builds the C++ service if `g++` is available.

<details>
<summary>The same steps by hand</summary>

```bat
copy backend\.env.example backend\.env
copy tote-frontend\.env.example tote-frontend\.env
copy packwise-frontend\.env.example packwise-frontend\.env

cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
deactivate
cd ..

cd tote-frontend && npm install && cd ..
cd packwise-frontend && npm install && cd ..

cd cpp-packer-service && build.bat && cd ..
```
</details>

## 4. Start everything

```bat
start-all.bat
```

It opens five windows. Or start each one yourself, in this order:

```bat
:: 1. C++ packing service
cd cpp-packer-service
build\packer_service.exe 8090

:: 2. API (new window)
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

:: 3. TOTE store (new window)
cd tote-frontend
npm run dev

:: 4. PackWise (new window)
cd packwise-frontend
npm run dev

:: 5. Simulator website (new window)
cd simulator-site
py -m http.server 5175
```

| Service | URL |
|---|---|
| TOTE store | http://localhost:5173 |
| PackWise | http://localhost:5174 |
| API + Swagger docs | http://localhost:8000/docs |
| Simulator website | http://localhost:5175 |
| C++ service health | http://127.0.0.1:8090/health |

The database is created and seeded the first time the API starts. Seeding only **adds** what is missing, so restarts never reset stock, prices or orders. To start over, stop the API and delete `backend\data\tote_packwise.db`.

## 5. Demo credentials

These come from `backend\.env` (copied from `.env.example`). Change them there; nothing is hard-coded in the apps.

| Who | Where | Sign in with |
|---|---|---|
| Customer | TOTE http://localhost:5173 | `demo@tote.local` / `DemoShopper-2026`, or register a new account |
| Warehouse worker | PackWise http://localhost:5174/login | any name + worker code `PACKWISE2026` |
| Admin | PackWise http://localhost:5174/admin/login | admin access code from `ADMIN_ACCESS_CODE` (example file: `ChangeMe-Admin-2026`) |

**Older `.env` files:** if yours has no `ADMIN_ACCESS_CODE` line, the value of your old `ADMIN_PASSWORD` line is used as the admin code, and the API window says so. To set your own code, add `ADMIN_ACCESS_CODE=your-code` to `backend\.env` and restart the API. The old email + password admin login is gone: admins use the code, and TOTE's `/admin` page has been removed from the shop.

## 6. Demo script for judges (about 5 minutes)

A ready-made order with the demo items is seeded on first start, but showing the full flow live is better:

1. **TOTE** — open http://localhost:5173, register a customer.
2. Add **Velvet Matte Lipstick**, **Gentle Nail Polish Remover**, **2 × Precision Liquid Eyeliner** and **Rose Oud Eau de Parfum** (use the search box).
3. **Bag → Checkout.** Fill the address, tick the simulated-payment box, place the order. Note the order code.
4. **PackWise** — open http://localhost:5174, sign in as a worker and click **Pack next order** (or open the order from the queue).
5. The carton is chosen automatically: **Box 6 · Medium Apparel / Electronics, 360 × 250 × 150 mm**. The carton shelf at the top shows all eight standard sizes to scale: six are too short for the 140 mm padded perfume, and the Large Multi-Item Box fits but is bigger. Below it: what to grab (the box, 1 bubble wrap, 1 poly bag, a few kraft sheets), the fragile and liquid warnings, and the planned layer in top view or 3D. *Why this carton?* lists the reasons and the honest warnings (nominal size used; no weight limit set).
   * Click **Start packing**. This reserves the carton and materials.
   * Follow the slides, one per product, in the engine's order. Each says what to wrap, where it goes ("Back-left corner", "Against the left wall, in front of 1"), and which way it faces, with the item highlighted in 3D (or **Top view**). The two eyeliners share one slide because the engine places them one after another. Use **Back**, the progress bar, or the ← → keys.
   * On **Fill, check and seal**, tap the three checks and **Complete packing**. Stock is consumed once and TOTE tracking updates.
   * **Pack next order** opens the next order in the queue.
6. Back on **TOTE → Orders**, the order now shows **Packed**. Mark it *Ready for dispatch* in PackWise and refresh TOTE.
7. Open the **admin console** (http://localhost:5174/admin/login, admin code). Show **Overview**, then **Orders → your order**: the 3D blueprint, the coordinate table taken from the engine JSON, the candidate cartons with each check, and the raw engine request and response. On **Cartons**, STD-06 stock went from 40 to 39 (see *History*). Edit STD-03 to record a measured internal size and watch it become *Verified*. Finish with **Reports & sustainability**.

**Show an honest no-fit:** order the **Cedar Reed Diffuser** (220 mm + 2 × 10 mm padding = 240 mm). The tallest standard carton is 200 mm, so PackWise refuses to choose one and suggests adding a carton at least 240 mm tall. Add one under **Cartons → Add custom carton** (for example 150 × 150 × 260 mm), open the order again in the worker queue and it packs. The ceramic bud vase (190 mm) shows the Large Multi-Item Box being used for a tall item.

**Show a carton change:** on the ready screen, **Change carton** lists only cartons that pass every check, smallest first (for the demo order, the Large Multi-Item Box), with how much bigger each is, the cost difference and one-tap reasons. The override is recorded and shows on the admin dashboard. **Stop packing** releases the reserved stock and brings back a fresh recommendation.

### How the worker screens map to the algorithm

* The recommendation is made automatically when an order is opened (same feasibility checks and C++ call as before).
* Slides are built from the plan's stored placements: one slide per product, grouping identical items only when the engine placed them consecutively, so the sequence is never reordered.
* Position wording comes from the placement edges (touching a wall) and from the earlier item each one touches in the engine output. Exact centimetres are under *Exact measurements*.
* The 3D view draws real x, y, footprint and height. Because the engine plans one layer with z = 0, the 3D view never stacks anything.
* The worker stands at the front: the carton's length runs left to right, as each screen says.

## 7. Packing rules (what the feasibility layer checks)

For each carton, in order:

1. **Active** — inactive cartons are skipped.
2. **Dimensions** (carton **internal** size) — each unit is inflated by its padding on every side (fragile items get at least `FRAGILE_MIN_PADDING_CM`, default 1 cm). Its padded height must fit the carton height (the engine keeps items upright), and its footprint must fit the floor in some 90° rotation.
3. **Weight** — total order weight must not exceed the carton's limit. A carton with no maximum weight configured is shown as *weight not checked* (a warning, not a pass).
4. **Placement** — the C++ engine must place every unit. For each carton it runs the original width search (200 row widths up to the carton side, both floor orientations) and keeps the tightest layout that fits. One HTTP call covers all candidate cartons.
5. **Carton stock** — available = stock − reserved must be at least 1.
6. **Protective materials** — product metadata says which material each unit needs (e.g. 1 bubble-wrap sheet per perfume). Void fill is an **estimate**: one kraft sheet per 2,000 cm³ of empty space (configurable). Fragile items with no protection rule block packing.

**Selection:** the smallest feasible carton (least volume); equal volumes go to the cheaper one. If cost data is missing the choice is unchanged and the cost shows as *Unavailable*.

**Units:** cartons are stored in whole millimetres; products in centimetres and grams. The engine works in whole millimetres; padded product sizes are rounded **up**, so rounding can only make a recommendation safer.

**Baseline and savings:** savings = baseline cost − recommended cost, where the baseline is the carton flagged as baseline (STD-07 Large Multi-Item Box by default; change it on the Cartons page), priced the same way, and only when it can physically hold the order. Negative savings are shown as negative. Each plan stores a frozen snapshot of the sizes and prices it used, so editing the catalogue later never changes past reports. Savings are counted once per order (completions are unique per order).

**Stock:** accepting a plan reserves stock with guarded `UPDATE … WHERE stock − reserved >= qty`, so two workers can never reserve the same carton. Cancelling or overriding releases reservations. Completing converts reservations into consumption exactly once (repeat requests return the same result without touching stock). Every change writes a stock-movement row.

**No-fit:** when no carton can hold an order, the plan lists why each carton failed and what could be done. Possible suggestions are a taller or larger carton (with the size needed), restocking a carton or material, or splitting the order. These suggestions come from the same checks; the engine never pretends to have packed it.

**Duplicate-safe checkout:** TOTE sends an `Idempotency-Key` with each checkout attempt. A double click or a retry returns the same order, without a second order or a second stock deduction. Packing completion was already idempotent.

**Not calculated:** CO₂ or emissions. Reports show cost, volume, utilisation, empty space and an estimated cardboard area.

## 8. Tests

```bat
cd backend
.venv\Scripts\activate
pytest -q
```

59 tests run against a temporary database **and the real C++ service** (the test fixture starts `cpp-packer-service\build\packer_service.exe` on a free port; build it first). They cover registration and password hashing, catalogue filters, cart stock checks, checkout and tracking, packer health and validation, an unreachable packer, the demo recommendation, padding, fragile minimums, weight limits, no-fit, floor overflow, carton and material shortages, missing cost data, reserve and release, competing reservations, five concurrent accepts, catalogue changes after planning, idempotent completion and exact consumption, protection enforcement, override validation, the eight standard cartons (exact names and sizes, idempotent seed, internal-size fitting, sample flags), custom cartons (validation, delete and deactivate rules, baseline rules), the cm → mm database migration, admin access code (sign-in, throttling, no leaks, logout, route protection), admin orders and reports, duplicate-safe checkout, snapshot persistence, no double-counted savings, dashboard counts, and role checks.

C++ core tests run as part of `build.bat`.

Simulator website: JavaScript port vs the original program (needs Node 18+ and g++):

```bat
cd simulator-site
node tests\equivalence.mjs
```

## 9. API overview

Full, interactive documentation is at http://localhost:8000/docs (click **Authorize** and paste a token from a login call).

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `/login` (customers), `/worker` (worker code), `/admin` (admin access code), `/logout`; `GET /api/auth/me` |
| Catalogue | `GET /api/products` (`q`, `category`, `min_price`, `max_price`, `sort`), `/categories`, `/{slug}` |
| Customer | `GET/PUT/DELETE /api/me/cart…`, `POST /api/me/cart/merge`, `/api/me/wishlist/{id}`, `/api/me/recent/{id}` |
| Orders | `POST /api/orders/checkout` (optional `Idempotency-Key` header), `GET /api/orders`, `GET /api/orders/{code}` |
| PackWise | `GET /api/packwise/summary`, `/orders`, `/orders/{id}`; `POST /orders/{id}/recommend`; `POST /plans/{id}/accept`, `/cancel`, `/override`, `/complete`; `POST /orders/{id}/dispatch` |
| Admin | `/products` (list, create, edit); `/cartons` (list, create, edit, `/adjust`, delete unused custom); `/materials`; `/movements`; `/orders` (filters) and `/orders/{id}` (items, plans, completion, overrides, audit); `/orders/{id}/priority`; `/dashboard`; `/reports` (`date_from`, `date_to`, `carton`, `q`); `/history`; `/audit`; `/overrides`; `/settings` |
| Health | `GET /api/health`, `GET /api/health/packer`, `GET /api/public/engine-preview` |

Roles are checked on the server: customers can only see their own orders; workers can pack but not open admin routes; admins can do everything.

## 10. Configuration (`backend\.env`)

| Variable | Default | Meaning |
|---|---|---|
| `PACKWISE_WORKER_CODE` | `PACKWISE2026` | Shared worker code. Empty disables worker sign-in. |
| `ADMIN_ACCESS_CODE` | | Code that opens the admin console. Empty = console locked (falls back to an old `ADMIN_PASSWORD` line if present) |
| `ADMIN_LOGIN_MAX_FAILURES`, `ADMIN_LOGIN_LOCKOUT_S` | `5`, `300` | Wrong-code throttle per computer |
| `SEED_SAMPLE_CARTON_VALUES` | `true` | Seed standard cartons with sample stock and prices (tagged *sample*) |
| `DEMO_CUSTOMER_PASSWORD` | | Creates `demo@tote.local` if set |
| `SEED_DEMO_ORDER` | `true` | Seed one demo order on the very first start |
| `PACKER_URL` | `http://127.0.0.1:8090` | Where FastAPI finds the C++ service |
| `FRAGILE_MIN_PADDING_CM` | `1.0` | Minimum padding for fragile items |
| `VOID_FILL_MATERIAL_CODE`, `VOID_FILL_CM3_PER_UNIT` | `KRAFT`, `2000` | Void-fill estimate rule |
| `CORS_ORIGINS` | both dev servers | Allowed browser origins |

Frontends read `VITE_API_URL` from their own `.env` (default `http://localhost:8000`).

## Deploying the full app

The two Vite frontends and FastAPI API can be deployed as separate Vercel projects from this repository. The C++ packing service runs as a container on a host that supports a long-running HTTP service. The API needs managed PostgreSQL in production; the local SQLite file is not durable serverless storage.

### Vercel projects

Create three Vercel projects connected to this GitHub repository:

| Project | Root Directory | Build settings | Required environment variables |
| --- | --- | --- | --- |
| TOTE storefront | `tote-frontend` | Vite; `npm run build`; output `dist` | `VITE_API_URL` = deployed API URL |
| PackWise warehouse | `packwise-frontend` | Vite; `npm run build`; output `dist` | `VITE_API_URL` = deployed API URL |
| FastAPI | `backend` | FastAPI/Python auto-detect | `DATABASE_URL`, `PACKER_URL`, `CORS_ORIGINS`, `PACKWISE_WORKER_CODE`, `ADMIN_ACCESS_CODE` |

Set `CORS_ORIGINS` on the API project to the two production frontend origins, comma-separated. Set `DATABASE_URL` to the provider's pooled PostgreSQL URL. Vercel runs FastAPI as request-based functions; do not point `PACKER_URL` at localhost. Store secrets in the Vercel dashboard, not in frontend variables. Only `VITE_API_URL` belongs in a frontend project.

### C++ packing service

For example, on Render create a Web Service from this repository, set the root directory to `cpp-packer-service`, choose Docker, and set the health check path to `/health`. The included Dockerfile binds to `0.0.0.0` and uses the host-provided `PORT`, as Render requires. Use the resulting public HTTPS URL as `PACKER_URL` in the FastAPI project. Another container host that supports a continuously running HTTP service can use the same Dockerfile.

### Database and first deployment

The API creates the current schema and seeds the sample catalogue when it starts. A new PostgreSQL database starts with the sample catalogue; it does not import the local SQLite database or its customer/order records. Add the required API secrets and production CORS origins, deploy the packing container, then deploy the API with its `DATABASE_URL` and `PACKER_URL`. Finally deploy both frontends with the API's public URL in `VITE_API_URL` and redeploy them whenever that build-time variable changes.

## 11. Project structure

```
tote-packwise/
├── backend/                 FastAPI + SQLite
│   ├── app/
│   │   ├── main.py          app, CORS, startup migration + seeding
│   │   ├── migrate.py       safe schema upgrades for older databases (cartons cm → mm, checkout key)
│   │   ├── models.py        tables
│   │   ├── schemas.py       request validation
│   │   ├── security.py      PBKDF2 passwords, session tokens, role checks
│   │   ├── seed.py          idempotent seed data (30 products, 8 standard cartons, materials)
│   │   ├── routers/         auth, catalog, shop, orders, packwise, admin, health, simulator, sim_public
│   │   └── services/        packer_client, feasibility, packing, inventory, orders, reports, audit
│   └── tests/               pytest suite
├── cpp-packer-service/      C++ HTTP microservice (original algorithm + adapter)
├── tote-frontend/           React storefront
├── packwise-frontend/       React warehouse app + admin console (src/pages/admin, components/AdminShell.jsx)
├── simulator-site/          Packing Simulator website (plain HTML, algorithm ported to JS)
├── setup.bat, start-all.bat
└── README.md
```

## 12. Design notes

* **TOTE** uses the burgundy / ivory / charcoal / sand palette with Bodoni Moda and Instrument Sans. Every product has an illustrated still-life drawn in SVG from its catalogue record, so the shop looks consistent and never shows broken images offline. An admin can set a real photo URL on any product to replace its illustration.
* **PackWise** uses inkberry / peach / peach-ivory / lavender with Archivo. The landing-page carton is drawn from a live call to the C++ engine; if the engine is down, it says so instead of drawing anything.
* Fonts load from Google Fonts; without internet the apps fall back to system fonts and still work.

## 13. Troubleshooting

| Symptom | Fix |
|---|---|
| PackWise says **"Packing engine offline"** | Start the C++ service (step 4.1). Check http://127.0.0.1:8090/health. |
| `'g++' is not recognized` | Add `C:\msys64\ucrt64\bin` to PATH and open a new Command Prompt, or use the prebuilt exe. |
| Windows Firewall prompt for `packer_service.exe` | Allow it on private networks; it only listens on 127.0.0.1. |
| **"Cannot reach the TOTE server"** in the browser | The API is not running on port 8000, or `VITE_API_URL` is wrong. |
| `Port 5173 is in use` | Close the other dev server, or change `server.port` in that app's `vite.config.js` and add the new origin to `CORS_ORIGINS`. |
| Worker code rejected | Check `PACKWISE_WORKER_CODE` in `backend\.env`, then restart the API. |
| Admin code rejected / console locked | Check `ADMIN_ACCESS_CODE` in `backend\.env` and restart the API. After 5 wrong tries, wait 5 minutes or restart the API. |
| Old cartons still recommended | Plans made before the upgrade keep their carton. Click **Change carton → Recalculate** (or Stop packing) to get a new recommendation from the eight standard cartons. |
| `pytest` skips packing tests | Build the C++ service first (`cpp-packer-service\build.bat`). |
| `python` opens the Microsoft Store | Turn off the "App execution aliases" for Python in Windows Settings, or reinstall Python with PATH ticked. |
| Want a clean database | Stop the API, delete `backend\data\tote_packwise.db`, start the API. |

## 14. Known limitations

* The engine plans one layer and keeps items upright; orders whose items could fit only by stacking or laying an item flat are reported as no-fit rather than guessed.
* Product sizes are simplified bounding boxes.
* Void-fill quantities are estimates from a configurable rule; actual usage is recorded at completion.
* Payment is simulated. No emissions figures are computed.
* Schema upgrades are handled by small explicit steps in `app/migrate.py` (not a general migration tool).
* The standard cartons' internal sizes, weight limits, stock and prices are not verified data: internal = nominal until measured, weight limits are unset, and stock and prices are tagged *sample*.
* Admin access is a single shared code (demo-level), with no per-person admin accounts.
* The 3D view draws bounding boxes, not product shapes.
