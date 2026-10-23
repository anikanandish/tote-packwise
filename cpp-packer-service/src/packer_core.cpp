// packer_core.cpp - see packer_core.hpp for what is original and what is new.
#include "packer_core.hpp"

#include <algorithm>
#include <cmath>
#include <ctime>
#include <limits>
#include <utility>

namespace packer {

using namespace std;

// ============================================================================
// ORIGINAL pack() - copied verbatim from packer.cpp (only made non-static).
// ============================================================================
Result pack(const vector<Item>& items, long long targetW) {
    Result r;
    r.p.resize(items.size());

    long long x = 0, y = 0, rowH = 0;
    long long usedW = 0, usedL = 0, maxBoxH = 0;

    for (const auto& it : items) {
        long long l = it.l, w = it.w;
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

        r.p[it.id] = {x, y, 0, l, w, it.h, rot};

        x += l;
        rowH = max(rowH, w);
        usedW = max(usedW, x);
        usedL = max(usedL, y + rowH);
        maxBoxH = max(maxBoxH, it.h);
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
void sortLikeOriginal(vector<Item>& items) {
    stable_sort(items.begin(), items.end(),
        [](const Item& a, const Item& b) {
            return max(a.l, a.w) > max(b.l, b.w);
        });
}

// ============================================================================
// ORIGINAL main() logic, moved into a function (I/O removed).
// ============================================================================
Result design(vector<Item> items) {
    const clock_t start = clock();

    long long area = 0, maxSide = 0, total = 0;
    for (const auto& it : items) {
        area += it.l * it.w;
        maxSide = max(maxSide, min(it.l, it.w));
    }

    sortLikeOriginal(items);

    for (const auto& item : items) {
        total += min(item.l, item.w);
    }

    const long long lo = max(
        maxSide,
        static_cast<long long>(sqrt(static_cast<long double>(area)))
    );
    const long long hi = max(lo, total);

    Result best;
    const int trials = 200;

    for (int k = 0; k < trials; ++k) {
        if (static_cast<double>(clock() - start) / CLOCKS_PER_SEC > 2.0) {
            break;
        }

        const long long width = lo + (hi - lo) * k / (trials - 1);
        Result candidate = pack(items, width);

        if (candidate.score < best.score) {
            best = move(candidate);
        }
    }
    return best;
}

// ============================================================================
// SIMULATION TRACE: identical to design() above, but keeps every candidate.
// ============================================================================
Trace designTrace(vector<Item> items) {
    const clock_t start = clock();
    Trace t;

    long long area = 0, maxSide = 0, total = 0;
    for (const auto& it : items) {
        area += it.l * it.w;
        maxSide = max(maxSide, min(it.l, it.w));
    }
    sortLikeOriginal(items);
    for (const auto& it : items) t.order.push_back(it.id);
    for (const auto& item : items) total += min(item.l, item.w);

    t.lo = max(maxSide, static_cast<long long>(sqrt(static_cast<long double>(area))));
    t.hi = max(t.lo, total);

    long double bestScore = numeric_limits<long double>::infinity();
    const int trials = 200;
    for (int k = 0; k < trials; ++k) {
        if (static_cast<double>(clock() - start) / CLOCKS_PER_SEC > 2.0) break;
        const long long width = t.lo + (t.hi - t.lo) * k / (trials - 1);
        Trial tr;
        tr.k = k;
        tr.width = width;
        tr.result = pack(items, width);
        tr.fits = std::isfinite(static_cast<double>(tr.result.score));
        if (tr.result.score < bestScore) {   // same strict comparison as design()
            bestScore = tr.result.score;
            t.best = static_cast<int>(t.trials.size());
        }
        t.trials.push_back(std::move(tr));
    }
    return t;
}

// ============================================================================
// EXTENSION: fixed-carton evaluation using the original pack() and the original
// width search. For one floor orientation of the carton:
//   * the rows may be at most `targetW` long (the carton side they run along),
//   * the rows may use at most `rowLimit` of the other side,
//   * no item may be taller than H (items are never tipped).
// The original main() sweep is run with its upper width limited to targetW:
// 200 widths from lo = max(largest short side, sqrt(total floor area)) up to
// targetW. Every layout that fits the carton is a candidate and the original
// score (W*L*H + 0.025*maxDim^2) picks the tightest one, exactly as design()
// does. pack() itself is not changed.
// ============================================================================
static CartonAttempt tryOrientation(const vector<Item>& sorted,
                                    const string& name,
                                    long long targetW, long long rowLimit,
                                    long long H) {
    CartonAttempt a;
    a.orientation = name;
    a.targetWidth = targetW;
    a.rowLimit = rowLimit;

    long long area = 0, maxSide = 0;
    for (const auto& it : sorted) {
        area += it.l * it.w;
        maxSide = max(maxSide, min(it.l, it.w));
    }
    long long lo = max(maxSide, static_cast<long long>(sqrt(static_cast<long double>(area))));
    lo = min(lo, targetW);
    const long long hi = targetW;

    const int trials = 200;
    Result best;
    for (int k = 0; k < trials; ++k) {
        const long long width = lo + (hi - lo) * k / (trials - 1);
        Result r = pack(sorted, width);
        ++a.widthsTried;
        if (!std::isfinite(static_cast<double>(r.score))) continue;
        if (r.W > targetW || r.L > rowLimit || r.H > H) continue;
        ++a.widthsThatFit;
        if (r.score < best.score) {          // same strict comparison as design()
            best = std::move(r);
            a.bestWidth = width;
        }
    }
    if (!best.p.empty() && std::isfinite(static_cast<double>(best.score))) {
        a.result = std::move(best);
        a.fits = true;
        return a;
    }

    // Nothing fits: explain using the widest layout (the carton's full side).
    a.result = pack(sorted, targetW);
    if (!std::isfinite(static_cast<double>(a.result.score))) {
        a.reason = "An item footprint is wider than " + to_string(targetW) +
                   " mm in both floor orientations";
    } else if (a.result.H > H) {
        a.reason = "Tallest item is " + to_string(a.result.H) +
                   " mm but carton height is " + to_string(H) +
                   " mm (items are never tipped over)";
    } else {
        a.reason = "Rows need " + to_string(a.result.L) + " mm but only " +
                   to_string(rowLimit) + " mm is available";
    }
    return a;
}

CartonFit fitCarton(vector<Item> items, long long L, long long W, long long H) {
    sortLikeOriginal(items);

    CartonFit fit;
    for (const auto& it : items) fit.sequence.push_back(it.id);

    // A: rows run along the carton length; rows stack up across the width.
    fit.attempts.push_back(tryOrientation(items, "rows_along_length", L, W, H));
    // B: rows run along the carton width; rows stack up along the length.
    fit.attempts.push_back(tryOrientation(items, "rows_along_width", W, L, H));

    // Of the two orientations, keep the tighter layout (lower original score).
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

}  // namespace packer
