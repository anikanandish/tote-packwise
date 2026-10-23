// packer_core.hpp
// -----------------------------------------------------------------------------
// The packing algorithm from the original packer.cpp, split out so it can be
// used by the HTTP service and by unit tests.
//
// WHAT IS ORIGINAL (unchanged logic):
//   * struct Item / Placement / Result
//   * pack(items, targetW)  -> row ("shelf") heuristic, copied verbatim
//   * design(items)         -> the width sweep that used to live in main()
//
// WHAT IS NEW (small, documented extension for carton integration):
//   * fitCarton(items, L, W, H) -> runs the ORIGINAL width search with pack()
//     inside one fixed carton: 200 row widths up to the carton side (both floor
//     orientations), keeps layouts that fit the carton's floor and height, and
//     picks the lowest original score. No new placement logic is introduced.
//
// TRUE CAPABILITIES (verified from the source):
//   * Single layer only: every placement has z = 0. Nothing is ever stacked.
//   * Items are never tipped over: an item's height always stays vertical.
//   * The only rotation is a 90 degree turn in the floor plane (swap l and w).
//   * No weight, padding, fragility, or inventory awareness - those are handled
//     by the FastAPI feasibility layer, never by this code.
//   * Integer units. The service uses millimetres.
// -----------------------------------------------------------------------------
#pragma once

#include <limits>
#include <string>
#include <vector>

namespace packer {

struct Item {
    long long l, w, h;
    int id;
};

struct Placement {
    long long x = 0, y = 0, z = 0;
    long long l = 0, w = 0, h = 0;
    bool rotated = false;
};

struct Result {
    long long W = 0, L = 0, H = 0;
    long double score = std::numeric_limits<long double>::infinity();
    std::vector<Placement> p;
};

// Original algorithm. `items` must already be sorted the way the original
// main() sorted them (see sortLikeOriginal) and ids must be 0..n-1.
Result pack(const std::vector<Item>& items, long long targetW);

// Original stable sort: largest footprint side first.
void sortLikeOriginal(std::vector<Item>& items);

// Original main() width sweep (200 trials, 2 second time budget).
// Designs the smallest-scoring bounding box for the items.
Result design(std::vector<Item> items);

// ----- Simulation trace (adapter): the SAME loop as design(), recording every trial.
// Calls the original pack() unchanged; the chosen trial is exactly design()'s result.
struct Trial {
    int k = 0;
    long long width = 0;
    bool fits = false;
    Result result;
};

struct Trace {
    long long lo = 0, hi = 0;
    std::vector<Trial> trials;
    int best = -1;                 // index into trials
    std::vector<int> order;        // item ids in the algorithm's placement order
};

Trace designTrace(std::vector<Item> items);

// ----- Extension: evaluate one fixed carton ---------------------------------
struct CartonAttempt {
    std::string orientation;   // "rows_along_length" or "rows_along_width"
    long long targetWidth = 0; // the targetW given to the original pack()
    long long rowLimit = 0;    // how much room the rows have
    bool fits = false;
    std::string reason;        // empty when it fits
    int widthsTried = 0;       // row widths given to pack()
    int widthsThatFit = 0;     // how many produced a layout inside the carton
    long long bestWidth = 0;   // row width of the kept layout
    Result result;             // raw pack() result in algorithm coordinates
};

struct CartonFit {
    bool fits = false;
    int chosen = -1;                     // index into attempts
    std::vector<CartonAttempt> attempts; // always 2 entries
    std::vector<int> sequence;           // item ids in placement order
};

// Carton internal dimensions: L (length), W (width), H (height).
CartonFit fitCarton(std::vector<Item> items, long long L, long long W, long long H);

}  // namespace packer
