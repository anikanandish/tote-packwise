// optimizer2_core.hpp - the cushion optimizer (original/optimizer2.cpp) as a library.
//
// ORIGINAL (copied verbatim from original/optimizer2.cpp, I/O removed):
//   * CUSION_TOTAL / CUSION_OFFSET, Item / Placement / Result
//   * pack(items, targetW): one layer of rows; fragile items take CUSION_TOTAL mm more on
//     every dimension (CUSION_OFFSET on each side); 90-degree floor rotation only
//   * main(): sort by longest floor side, 200 widths from lo to hi, lowest score wins
//     -> design(items)
// NEW:
//   * fitCarton(items, L, W, H): the same 200-width search limited to one fixed carton
//     (widths up to the carton side the rows run along; the rows must fit the other side and
//     the tallest item, cushion included, must fit the height). Both floor orientations,
//     lowest original score kept. pack() itself is not changed.
#pragma once

#include <limits>
#include <string>
#include <vector>

namespace optimizer2 {

const long long CUSION_TOTAL = 15;
const double CUSION_OFFSET = 7.5;

struct Item {
    long long l, w, h;
    int id;
    bool fragile = false;
};

struct Placement {
    long long x = 0, y = 0, z = 0;
    long long l = 0, w = 0, h = 0;
    bool rotated = false;
    bool fragile = false;
};

struct Result {
    long long W = 0, L = 0, H = 0;
    long double score = std::numeric_limits<long double>::infinity();
    std::vector<Placement> p;
};

Result pack(const std::vector<Item>& items, long long targetW);
void sortLikeOptimizer2(std::vector<Item>& items);
Result design(std::vector<Item> items);

struct CartonAttempt {
    std::string orientation;
    long long targetWidth = 0;
    long long rowLimit = 0;
    bool fits = false;
    std::string reason;
    int widthsTried = 0;
    int widthsThatFit = 0;
    long long bestWidth = 0;
    Result result;
};

struct CartonFit {
    bool fits = false;
    int chosen = -1;
    std::vector<CartonAttempt> attempts;
    std::vector<int> sequence;
};

CartonFit fitCarton(std::vector<Item> items, long long L, long long W, long long H);

}  // namespace optimizer2
