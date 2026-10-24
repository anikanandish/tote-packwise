// Unit tests for the packing core (no HTTP). Build with build.bat / build.sh.
#include <array>
#include <cassert>
#include <iostream>

#include "../src/packer_core.hpp"
#include "../src/optimizer_core.hpp"
#include "../src/optimizer2_core.hpp"

using namespace packer;

static int failures = 0;
#define CHECK(cond)                                                         \
    do {                                                                    \
        if (!(cond)) {                                                      \
            std::cerr << "FAIL line " << __LINE__ << ": " #cond << "\n";    \
            ++failures;                                                     \
        }                                                                   \
    } while (0)

static bool noOverlap(const Result& r, size_t n) {
    for (size_t i = 0; i < n; ++i)
        for (size_t j = i + 1; j < n; ++j) {
            const auto& a = r.p[i];
            const auto& b = r.p[j];
            const bool sep = a.x + a.l <= b.x || b.x + b.l <= a.x ||
                             a.y + a.w <= b.y || b.y + b.w <= a.y;
            if (!sep) return false;
        }
    return true;
}

int main() {
    // 1. Original design mode still works and keeps z = 0.
    {
        std::vector<Item> items = {{40, 30, 10, 0}, {20, 20, 15, 1}, {50, 10, 5, 2}};
        Result r = design(items);
        CHECK(!r.p.empty());
        CHECK(r.H == 15);
        CHECK(noOverlap(r, items.size()));
        for (const auto& p : r.p) CHECK(p.z == 0);
    }
    // 2. Fits a roomy carton.
    {
        std::vector<Item> items = {{100, 60, 140, 0}, {80, 60, 140, 1}, {25, 25, 85, 2}};
        CartonFit f = fitCarton(items, 300, 200, 150);
        CHECK(f.fits);
        CHECK(f.sequence.size() == 3);
    }
    // 3. Too tall - items are never tipped.
    {
        std::vector<Item> items = {{20, 20, 130, 0}};
        CartonFit f = fitCarton(items, 200, 150, 100);
        CHECK(!f.fits);
        CHECK(f.attempts[0].reason.find("height") != std::string::npos);
    }
    // 4. Footprint too wide in both orientations.
    {
        std::vector<Item> items = {{400, 400, 10, 0}};
        CartonFit f = fitCarton(items, 300, 200, 150);
        CHECK(!f.fits);
    }
    // 5. Rows overflow the carton.
    {
        std::vector<Item> items;
        for (int i = 0; i < 12; ++i) items.push_back({100, 100, 50, i});
        CartonFit f = fitCarton(items, 300, 200, 150);  // only 6 fit on the floor
        CHECK(!f.fits);
    }
    // 6. Rotation is used when needed: 250x90 item in a 100-wide floor dimension.
    {
        std::vector<Item> items = {{90, 250, 10, 0}};
        CartonFit f = fitCarton(items, 300, 100, 50);
        CHECK(f.fits);
    }
    // 7. Simulation trace picks exactly what design() picks.
    {
        std::vector<Item> items = {{100, 70, 140, 0}, {70, 50, 140, 1}, {25, 25, 85, 2}, {15, 15, 130, 3}, {15, 15, 130, 4}};
        Result d = design(items);
        Trace t = designTrace(items);
        CHECK(t.best >= 0);
        const Result& b = t.trials[t.best].result;
        CHECK(b.W == d.W && b.L == d.L && b.H == d.H);
        for (size_t i = 0; i < items.size(); ++i)
            CHECK(b.p[i].x == d.p[i].x && b.p[i].y == d.p[i].y && b.p[i].rotated == d.p[i].rotated);
        CHECK(t.trials.size() <= 200);
    }
    // 8. The width search inside a carton finds a layout the full-width pass misses.
    {
        std::vector<Item> items = {{52, 97, 29, 0}, {106, 40, 49, 1}, {26, 84, 51, 2}};
        auto sorted = items;
        sortLikeOriginal(sorted);
        Result a = pack(sorted, 164), b = pack(sorted, 178);
        CHECK(!(a.L <= 178) && !(b.L <= 164));          // full width fails both ways
        CartonFit f = fitCarton(items, 164, 178, 100);
        CHECK(f.fits);
        const auto& r = f.attempts[f.chosen];
        CHECK(r.result.W <= r.targetWidth && r.result.L <= r.rowLimit);
        CHECK(noOverlap(r.result, items.size()));
        CHECK(r.widthsTried == 200 && r.widthsThatFit >= 1);
    }
    // 9. Whatever fits stays inside the carton.
    {
        std::vector<Item> items = {{100, 60, 140, 0}, {80, 60, 140, 1}, {25, 25, 85, 2}, {40, 30, 20, 3}};
        CartonFit f = fitCarton(items, 300, 200, 150);
        CHECK(f.fits);
        for (const auto& a : f.attempts)
            if (a.fits) CHECK(a.result.W <= a.targetWidth && a.result.L <= a.rowLimit && a.result.H <= 150);
    }
    // ---------------- optimizer (original/optimizer.cpp) ----------------
    {
        namespace O = optimizer;
        // 10. Stays inside the carton (cushion included) and nothing overlaps in 3D.
        std::vector<O::Item> items = {{100, 70, 140, 0}, {70, 50, 140, 1}, {25, 25, 85, 2}, {15, 15, 130, 3},
                                      {40, 40, 60, 4, true}, {60, 60, 50, 5, true}};
        O::CartonFit f = O::fitCarton(items, 360, 250, 150);
        CHECK(f.fits);
        const auto& a = f.attempts[f.chosen];
        std::vector<std::array<long long, 6>> box;
        for (size_t i = 0; i < items.size(); ++i) {
            const auto& p = a.result.p[i];
            const long long pad = items[i].fragile ? O::CUSHION_TOTAL : 0;
            const double off = items[i].fragile ? O::CUSHION_OFFSET : 0.0;
            box.push_back({(long long)(p.x - off), (long long)(p.y - off), (long long)(p.z - off),
                           p.l + pad, p.w + pad, p.h + pad});
            CHECK(box.back()[0] >= 0 && box.back()[0] + box.back()[3] <= a.targetWidth);
            CHECK(box.back()[1] >= 0 && box.back()[1] + box.back()[4] <= a.rowLimit);
            CHECK(box.back()[2] >= 0 && box.back()[2] + box.back()[5] <= 150);
            CHECK(p.h == items[i].h);                       // never tipped over
        }
        for (size_t i = 0; i < box.size(); ++i)
            for (size_t j = i + 1; j < box.size(); ++j) {
                const auto& u = box[i]; const auto& v = box[j];
                const bool sep = u[0] + u[3] <= v[0] || v[0] + v[3] <= u[0] || u[1] + u[4] <= v[1] ||
                                 v[1] + v[4] <= u[1] || u[2] + u[5] <= v[2] || v[2] + v[5] <= u[2];
                CHECK(sep);
            }
    }
    {
        namespace O = optimizer;
        // 11. Stacks in layers when the floor is too small for one layer.
        std::vector<O::Item> items;
        for (int i = 0; i < 4; ++i) items.push_back({100, 100, 40, i});
        O::CartonFit f = O::fitCarton(items, 200, 100, 100);   // floor holds 2, height holds 2 layers
        CHECK(f.fits);
        bool stacked = false;
        for (const auto& p : f.attempts[f.chosen].result.p) if (p.z > 0) stacked = true;
        CHECK(stacked);
        // 12. Too tall (cushion counts) -> rejected.
        std::vector<O::Item> tall = {{50, 50, 80, 0, true}};      // 80 + 30 = 110 > 100
        CHECK(!O::fitCarton(tall, 200, 150, 100).fits);
        // 13. optimizeDesign() packs and scores like the program.
        O::Result d = O::optimizeDesign({{100, 70, 140, 0}, {25, 25, 85, 1, true}});
        CHECK(d.success && d.W >= 180 && d.L >= 100 && d.H >= 50);
    }
    // ---------------- optimizer2 (original/optimizer2.cpp) ----------------
    {
        namespace P = optimizer2;
        std::vector<P::Item> items = {{100, 70, 125, 0}, {60, 40, 130, 1}, {25, 25, 85, 2}, {80, 50, 120, 3, true}};
        P::CartonFit f = P::fitCarton(items, 360, 250, 150);
        CHECK(f.fits);
        const auto& a = f.attempts[f.chosen];
        CHECK(a.result.W <= a.targetWidth && a.result.L <= a.rowLimit && a.result.H <= 150);
        CHECK(a.result.H == 135);                                  // fragile 120 + 15 cushion
        // too tall once the cushion is added: 120 + 15 > 130
        std::vector<P::Item> tall = {{80, 50, 120, 0, true}};
        CHECK(!P::fitCarton(tall, 300, 200, 130).fits);
        CHECK(P::fitCarton(tall, 300, 200, 135).fits);
    }
    if (failures == 0) std::cout << "All core tests passed\n";
    return failures == 0 ? 0 : 1;
}
