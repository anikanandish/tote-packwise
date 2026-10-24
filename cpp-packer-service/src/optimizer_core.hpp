// optimizer_core.hpp - the new PackWise optimizer (original/optimizer.cpp) as a library.
//
// What is ORIGINAL (copied verbatim from original/optimizer.cpp, I/O removed):
//   * constants CUSHION_TOTAL, CUSHION_OFFSET, MAX_H and the Item/Placement/Result structs
//   * pack3D(items, targetW, targetL, maxH)  - rows -> layers -> stacked layers, fragile cushion
//   * the sort by footprint area and the search in main(): 60 widths spaced geometrically from
//     lo to hiDim, and for each width a binary search on the length; lowest score wins.
//     -> optimizeDesign(items) is main() as a function (designs a box, like the program does).
//
// What is NEW (so the optimizer can choose among the warehouse's fixed cartons):
//   * fitCarton(items, L, W, H): runs the SAME search, but limited to one carton: widths go up
//     to the carton side the rows run along, the length search stops at the other side and the
//     stack may not be taller than the carton (nor MAX_H). Both floor orientations are tried
//     and the lower original score is kept. pack3D() itself is not changed.
#pragma once

#include <limits>
#include <string>
#include <vector>

namespace optimizer {

// ---- ORIGINAL constants and types (optimizer.cpp) ----
const long long CUSHION_TOTAL = 30;
const double CUSHION_OFFSET = 15.0;
const long long MAX_H = 300;

struct Item {
    long long l, w, h;
    int id;
    bool fragile = false;
};

struct Placement {
    double x = 0.0, y = 0.0, z = 0.0;
    long long l = 0, w = 0, h = 0;
    bool rotated = false;
};

struct Result {
    long long W = 0, L = 0, H = 0;
    long double score = std::numeric_limits<long double>::infinity();
    std::vector<Placement> p;
    bool success = false;
};

// ORIGINAL pack3D, verbatim.
Result pack3D(const std::vector<Item>& items, long long targetW, long long targetL, long long maxH);

// ORIGINAL sort from main(): footprint area, largest first (stable).
void sortLikeOptimizer(std::vector<Item>& items);

// ORIGINAL main() search as a function. success == false when nothing fits.
Result optimizeDesign(std::vector<Item> items);

// ---- NEW: fixed-carton evaluation ----
struct CartonAttempt {
    std::string orientation;    // "rows_along_length" or "rows_along_width"
    long long targetWidth = 0;  // carton side the rows run along (upper limit of the width search)
    long long rowLimit = 0;     // carton side the rows stack along (upper limit of the length search)
    long long maxH = 0;         // min(carton height, MAX_H)
    bool fits = false;
    std::string reason;
    int widthsTried = 0;        // widths given to the search
    int widthsThatFit = 0;      // widths for which some length fitted inside the carton
    long long bestWidth = 0;
    long long bestLength = 0;
    Result result;              // pack3D result, algorithm coordinates
};

struct CartonFit {
    bool fits = false;
    int chosen = -1;
    std::vector<CartonAttempt> attempts;  // always 2 entries
    std::vector<int> sequence;            // item ids in placement order
};

CartonFit fitCarton(std::vector<Item> items, long long L, long long W, long long H);

}  // namespace optimizer
