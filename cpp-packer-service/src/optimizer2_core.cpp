// optimizer2_core.cpp - see optimizer2_core.hpp for what is original and what is new.
#include "optimizer2_core.hpp"

#include <algorithm>
#include <cmath>
#include <ctime>
#include <utility>

namespace optimizer2 {

using namespace std;

// ============================================================================
// ORIGINAL pack() - copied verbatim from optimizer2.cpp (only made non-static).
// ============================================================================
Result pack(const vector<Item>& items, long long targetW) {
    Result r;
    r.p.resize(items.size());

    long long x = 0, y = 0, rowH = 0;
    long long usedW = 0, usedL = 0, maxBoxH = 0;

    for (auto const & it : items) {
        const long long pad = it.fragile ? CUSION_TOTAL : 0;
        long long l = it.l + pad, w = it.w + pad;
        bool rot = false;

        if (l > targetW && w <= targetW) {
            swap(l, w);
            rot = true;
        }
        if (l > targetW) return r;

        if (x > 0) {
            const bool normalFits = x + l <= targetW;
            const bool rotatedFits = x + w <= targetW && w <= targetW;

            if (!normalFits && rotatedFits) {
                swap(l, w);
                rot = !rot;
            } else if (normalFits && rotatedFits &&
                       w < l && x + l > targetW * 3 / 4) {
                swap(l, w);
                rot = !rot;
            }
        }

        if (x > 0 && x + l > targetW) {
            y += rowH;
            x = 0;
            rowH = 0;
        }
        if (l > targetW) return r;

        r.p[it.id] = {x, y, 0, l - pad, w - pad, it.h, rot, it.fragile};

        x += l;
        rowH = max(rowH, w);
        usedW = max(usedW, x);
        usedL = max(usedL, y + rowH);
        maxBoxH = max(maxBoxH, it.h + pad);
    }

    r.W = usedW;
    r.L = usedL;
    r.H = maxBoxH;

    const long double maxDim = max({usedW, usedL, maxBoxH});
    r.score = static_cast<long double>(usedW) * usedL * maxBoxH
            + 0.025L * maxDim * maxDim;

    return r;
}

// ORIGINAL sort from main().
void sortLikeOptimizer2(vector<Item>& items) {
    stable_sort(items.begin(), items.end(),
        [](const Item& a, const Item& b) {
            return max(a.l, a.w) > max(b.l, b.w);
        });
}

// lo / hi exactly as main() computes them (cushion included).
static void bounds(const vector<Item>& items, long long& lo, long long& hi) {
    long long area = 0, maxSide = 0, total = 0;
    for (const auto& it : items) {
        const long long pad = it.fragile ? CUSION_TOTAL : 0;
        area += (it.l + pad) * (it.w + pad);
        maxSide = max(maxSide, min(it.l, it.w) + pad);
    }
    for (const auto& item : items) {
        total += min(item.l, item.w) + (item.fragile ? CUSION_TOTAL : 0);
    }
    lo = max(maxSide, static_cast<long long>(sqrt(static_cast<long long>(area))));
    hi = max(lo, total);
}

// ============================================================================
// ORIGINAL main() search as a function (I/O removed).
// ============================================================================
Result design(vector<Item> items) {
    const clock_t start = clock();
    long long lo, hi;
    bounds(items, lo, hi);
    sortLikeOptimizer2(items);

    Result best;
    const int trials = 200;
    for (int k = 0; k < trials; ++k) {
        if (static_cast<double>(clock() - start) / CLOCKS_PER_SEC > 2.0) break;
        const long long width = lo + (hi - lo) * k / (trials - 1);
        Result candidate = pack(items, width);
        if (candidate.score < best.score) best = move(candidate);
    }
    return best;
}

// ============================================================================
// NEW: the same search inside one fixed carton (one floor orientation).
// ============================================================================
static CartonAttempt tryOrientation(const vector<Item>& sorted, const string& name,
                                    long long targetW, long long rowLimit, long long H) {
    CartonAttempt a;
    a.orientation = name;
    a.targetWidth = targetW;
    a.rowLimit = rowLimit;

    long long lo, hi;
    bounds(sorted, lo, hi);
    lo = min(lo, targetW);
    hi = targetW;

    const int trials = 200;
    Result best;
    for (int k = 0; k < trials; ++k) {
        const long long width = lo + (hi - lo) * k / (trials - 1);
        Result r = pack(sorted, width);
        ++a.widthsTried;
        if (!std::isfinite(static_cast<double>(r.score))) continue;
        if (r.W > targetW || r.L > rowLimit || r.H > H) continue;
        ++a.widthsThatFit;
        if (r.score < best.score) {          // same strict comparison as main()
            best = move(r);
            a.bestWidth = width;
        }
    }
    if (!best.p.empty() && std::isfinite(static_cast<double>(best.score))) {
        a.result = move(best);
        a.fits = true;
        return a;
    }
    Result wide = pack(sorted, targetW);
    if (!std::isfinite(static_cast<double>(wide.score))) {
        a.reason = "An item footprint (with cushion) is wider than " + to_string(targetW) +
                   " mm in both floor orientations";
    } else if (wide.H > H) {
        a.reason = "Tallest item needs " + to_string(wide.H) + " mm (with cushion) but carton height is " +
                   to_string(H) + " mm (items are never tipped over)";
    } else {
        a.reason = "Rows need " + to_string(wide.L) + " mm but only " + to_string(rowLimit) +
                   " mm is available";
    }
    return a;
}

CartonFit fitCarton(vector<Item> items, long long L, long long W, long long H) {
    sortLikeOptimizer2(items);
    CartonFit fit;
    for (const auto& it : items) fit.sequence.push_back(it.id);
    fit.attempts.push_back(tryOrientation(items, "rows_along_length", L, W, H));
    fit.attempts.push_back(tryOrientation(items, "rows_along_width", W, L, H));
    long double bestScore = numeric_limits<long double>::infinity();
    for (int i = 0; i < static_cast<int>(fit.attempts.size()); ++i) {
        const auto& a = fit.attempts[i];
        if (a.fits && a.result.score < bestScore) {
            bestScore = a.result.score;
            fit.chosen = i;
        }
    }
    fit.fits = fit.chosen >= 0;
    return fit;
}

}  // namespace optimizer2
