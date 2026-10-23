# PackWise C++ packing service

A standalone HTTP microservice around the original `packer.cpp` algorithm.
FastAPI calls it over HTTP; it never runs inside Python.

| Item | Value |
|---|---|
| Default address | `http://127.0.0.1:8090` |
| Change port | `packer_service.exe 9000` or set `PACKER_PORT` |
| Change host | second argument or `PACKER_HOST` |
| Libraries | [cpp-httplib](https://github.com/yhirose/cpp-httplib) 0.18.3 and [nlohmann/json](https://github.com/nlohmann/json) 3.11.3, both MIT, single headers already in `include/` |
| Units | integer **millimetres** |

## What is original and what is new

`original/packer.cpp` is your file, untouched. `src/packer_core.cpp` contains:

* `pack(items, targetW)` — **copied verbatim** from `packer.cpp`.
* `design(items)` — the original `main()` width sweep (200 trials, 2-second budget), with stdin/stdout removed. It produces exactly the same output as the original program (checked: input `40 30 10 / 20 20 15 / 50 10 5 / 25 35 8` gives box `50 75 15` and identical placements in both).
* `fitCarton(items, L, W, H)` — **the only extension**. For each floor orientation it runs the original width search inside the carton: `pack()` at 200 widths from the original lower bound (largest short side, or √area) up to the carton side. Layouts that fit the other floor side and the height are kept and the original score picks the tightest. It reports why each orientation failed, plus `widths_tried`, `widths_that_fit` and `best_width`. No new placement logic.

### What the algorithm can and cannot do (verified from the source)

* **Single layer.** Every placement has `z = 0`. It never stacks.
* **Upright only.** An item's height is never rotated, so items are never tipped over.
* **90° floor rotation.** It may swap an item's length and width to fit a row.
* **Row (shelf) heuristic.** Items are sorted by their longest floor side and placed left to right; when a row is full a new row starts behind it. Row depth is the deepest item in that row.
* **No weight, padding, fragility or stock awareness.** The FastAPI feasibility layer handles those and inflates item sizes by their padding before calling this service.
* The original program designs a box for the items. It does not evaluate fixed cartons, which is why `fitCarton` was added.

## Build

**Windows (MSYS2 MinGW-w64):**

```bat
cd cpp-packer-service
build.bat
```

`build.bat` compiles `build\packer_service.exe` and `build\test_core.exe`, then runs the core tests.

**Windows (Visual Studio Build Tools + CMake):**

```bat
cmake -S . -B build
cmake --build build --config Release
```

**Linux / macOS:** `./build.sh`

**No compiler yet?** `prebuilt\packer_service.exe` was compiled from this exact source with
`x86_64-w64-mingw32-g++ -std=c++17 -O2 -D_WIN32_WINNT=0x0A00 -Iinclude -Isrc src/main.cpp src/packer_core.cpp -lws2_32 -lcrypt32 -static`.
It was cross-compiled and not executed on Windows, so build your own when you can.

## Run

```bat
build\packer_service.exe 8090
```

## API

### `GET /health`

```json
{"status":"ok","service":"packwise-packer","version":"1.0.0",
 "capabilities":{"layers":"single","stacking":false,"tipping_items":false,"floor_rotation_90deg":true,
                 "weight_aware":false,"padding_aware":false,"units":"mm","modes":["cartons","design"]}}
```

### `POST /v1/pack/cartons` — evaluate fixed cartons (used by FastAPI)

Request:

```json
{
  "items":   [{"id": "P4-1", "l": 100, "w": 70, "h": 140}, {"id": "P1-1", "l": 25, "w": 25, "h": 85}],
  "cartons": [{"id": "C2", "l": 200, "w": 150, "h": 100}, {"id": "C3", "l": 300, "w": 200, "h": 150}]
}
```

Response (shortened):

```json
{
  "mode": "cartons",
  "frame": "x along carton length, y along carton width, z up; mm",
  "results": [
    {"carton_id": "C2", "fits": false,
     "attempts": [{"orientation": "rows_along_length", "fits": false,
                   "reason": "Tallest item is 140 mm but carton height is 100 mm (items are never tipped over)"}, "..."]},
    {"carton_id": "C3", "fits": true, "orientation": "rows_along_length",
     "used": {"x": 125, "y": 70, "z": 140},
     "placements": [{"id": "P4-1", "seq": 1, "x": 0, "y": 0, "z": 0, "dx": 100, "dy": 70, "dz": 140, "rotated": false}, "..."]}
  ]
}
```

`seq` is the order the algorithm placed items (the packer follows it). `dx`, `dy`, `dz` are the extents in the carton frame.

### `POST /v1/pack/design` — original behaviour

Same `items` array; returns the designed box `{"W","L","H"}`, `score` and placements, exactly like the original program.

### Errors

Always JSON with HTTP 400 (bad input), 404 or 500:

```json
{"error": {"code": "invalid_dimension", "message": "items[0].l must be between 1 and 100000 mm"}}
```

Codes: `malformed_json`, `missing_field`, `invalid_dimension`, `invalid_id`, `duplicate_id`, `invalid_items`, `invalid_cartons`, `no_solution`.

## Test it on its own

```bat
curl http://127.0.0.1:8090/health
curl -X POST http://127.0.0.1:8090/v1/pack/cartons -H "Content-Type: application/json" -d "{\"items\":[{\"id\":\"a\",\"l\":100,\"w\":70,\"h\":140}],\"cartons\":[{\"id\":\"L\",\"l\":300,\"w\":200,\"h\":150}]}"
```
