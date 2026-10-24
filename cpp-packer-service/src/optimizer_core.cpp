// optimizer_core.cpp - see optimizer_core.hpp for what is original and what is new.
#include "optimizer_core.hpp"

#include <algorithm>
#include <cmath>
#include <ctime>
#include <utility>

namespace optimizer {

using namespace std;

// ============================================================================
// ORIGINAL pack3D() - copied verbatim from optimizer.cpp (only made non-static).
// ============================================================================
Result pack3D(const vector<Item>& items, long long targetW,
              long long targetL, long long maxH) {
    Result r;
    r.p.resize(items.size());

    long long current_x = 0, current_y = 0, current_z = 0;
    long long row_max_l = 0, layer_max_h = 0;
    long long final_W = 0, final_L = 0, final_H = 0;

    for (auto const & it : items) {
        long long pad = it.fragile ? CUSHION_TOTAL : 0;
        long long target_l = it.l + pad;
        long long target_w = it.w + pad;
        long long target_h = it.h + pad;
        bool rot = false;

        if (target_h > maxH) return r;

        if (target_l > targetW && target_w <= targetW) {
            swap(target_l, target_w);
            rot = true;
        }

        if (target_l > targetW || target_w > targetL) return r;

        if (current_x + target_l > targetW) {
            current_y += row_max_l;
            current_x = 0;
            row_max_l = 0;
        }

        if (current_y + target_w > targetL) {
            current_z += layer_max_h;
            current_x = 0;
            current_y = 0;
            row_max_l = 0;
            layer_max_h = 0;
        }

        if (current_x + target_l > targetW || current_y + target_w > targetL) return r;
        if (current_z + target_h > maxH) return r;

        double final_x = static_cast<double>(current_x) + (it.fragile ? CUSHION_OFFSET : 0.0);
        double final_y = static_cast<double>(current_y) + (it.fragile ? CUSHION_OFFSET : 0.0);
        double final_z = static_cast<double>(current_z) + (it.fragile ? CUSHION_OFFSET : 0.0);

        r.p[it.id] = {
            final_x, final_y, final_z,
            rot ? it.w : it.l,
            rot ? it.l : it.w,
            it.h, rot
        };

        current_x += target_l;
        row_max_l = max(row_max_l, target_w);
        layer_max_h = max(layer_max_h, target_h);

        final_W = max(final_W, current_x);
        final_L = max(final_L, current_y + row_max_l);
        final_H = max(final_H, current_z + layer_max_h);
    }

    r.W = final_W;
    r.L = final_L;
    r.H = final_H;

    if (r.W > 0 && r.W < 180) r.W = 180;
    if (r.L > 0 && r.L < 100) r.L = 100;
    if (r.H > 0 && r.H < 50)  r.H = 50;

    long double volume = static_cast<long double>(r.W) * r.L * r.H;
    long double maxDim = max({r.W, r.L, r.H});
    r.score = volume + 0.025L * maxDim * maxDim;
    r.success = true;

    return r;
}

// ORIGINAL sort from main().
void sortLikeOptimizer(vector<Item>& items) {
    stable_sort(items.begin(), items.end(), [](const Item& a, const Item& b) {
        return (a.l * a.w) > (b.l * b.w);
    });
}

// ============================================================================
// ORIGINAL main() search, moved into a function (I/O removed).
// ============================================================================
Result optimizeDesign(vector<Item> items) {
    const clock_t start_time = clock();

    long long lo = 1, hiDim = 0;
    for (const auto& it : items) {
        long long pad = it.fragile ? CUSHION_TOTAL : 0;
        long long pl = it.l + pad, pw = it.w + pad, ph = it.h + pad;
        if (ph > MAX_H) return Result{};
        lo = max(lo, min(pl, pw));
        hiDim += max(pl, pw);
    }
    hiDim = max(hiDim, lo);

    sortLikeOptimizer(items);

    Result best_result;
    const int samples = 60;

    for (int k = 0; k < samples; ++k) {
        if ((static_cast<double>(clock() - start_time) / CLOCKS_PER_SEC) > 1.90) break;

        double t = samples > 1 ? static_cast<double>(k) / (samples - 1) : 0.0;
        long long W = llround(lo * pow(static_cast<double>(hiDim) / lo, t));

        if (!pack3D(items, W, hiDim, MAX_H).success) continue;

        long long loL = lo, hiL = hiDim, bestL = hiDim;
        while (loL <= hiL) {
            long long midL = loL + (hiL - loL) / 2;
            if (pack3D(items, W, midL, MAX_H).success) {
                bestL = midL;
                hiL = midL - 1;
            } else {
                loL = midL + 1;
            }
        }

        Result candidate = pack3D(items, W, bestL, MAX_H);
        if (candidate.success && candidate.score < best_result.score) {
            best_result = move(candidate);
        }
    }
    return best_result;
}

// ============================================================================
// NEW: the same search, limited to one fixed carton.
//   widths:  60 geometric samples from lo up to min(hiDim, the side the rows run along)
//   length:  must fit the other side; the original binary search finds the shortest
//   height:  pack3D's maxH = min(carton height, MAX_H)
// Every layout pack3D accepts therefore lies inside the carton.
// ============================================================================
static CartonAttempt tryOrientation(const vector<Item>& sorted, const string& name,
                                    long long sideA, long long sideB, long long H) {
    const clock_t start_time = clock();
    CartonAttempt a;
    a.orientation = name;
    a.targetWidth = sideA;
    a.rowLimit = sideB;
    a.maxH = min(H, MAX_H);

    long long lo = 1, hiDim = 0, tallest = 0;
    for (const auto& it : sorted) {
        long long pad = it.fragile ? CUSHION_TOTAL : 0;
        long long pl = it.l + pad, pw = it.w + pad, ph = it.h + pad;
        tallest = max(tallest, ph);
        lo = max(lo, min(pl, pw));
        hiDim += max(pl, pw);
    }
    hiDim = max(hiDim, lo);

    if (tallest > a.maxH) {
        a.reason = "Tallest item needs " + to_string(tallest) + " mm (with cushion) but only " +
                   to_string(a.maxH) + " mm of height is available (items are never tipped over)";
        return a;
    }
    const long long hiW = min(hiDim, sideA);
    if (lo > hiW) {
        a.reason = "An item footprint needs " + to_string(lo) + " mm but rows can only be " +
                   to_string(sideA) + " mm long";
        return a;
    }

    Result best;
    const int samples = 60;
    for (int k = 0; k < samples; ++k) {
        if ((static_cast<double>(clock() - start_time) / CLOCKS_PER_SEC) > 1.90) break;

        double t = samples > 1 ? static_cast<double>(k) / (samples - 1) : 0.0;
        long long W = llround(lo * pow(static_cast<double>(hiW) / lo, t));
        ++a.widthsTried;

        if (!pack3D(sorted, W, sideB, a.maxH).success) continue;
        ++a.widthsThatFit;

        long long loL = lo, hiL = min(hiDim, sideB), bestL = sideB;
        while (loL <= hiL) {
            long long midL = loL + (hiL - loL) / 2;
            if (pack3D(sorted, W, midL, a.maxH).success) {
                bestL = midL;
                hiL = midL - 1;
            } else {
                loL = midL + 1;
            }
        }

        Result candidate = pack3D(sorted, W, bestL, a.maxH);
        if (candidate.success && candidate.score < best.score) {   // same strict comparison as main()
            best = move(candidate);
            a.bestWidth = W;
            a.bestLength = bestL;
        }
    }
    if (best.success) {
        a.result = move(best);
        a.fits = true;
    } else {
        a.reason = "Items do not fit in " + to_string(sideA) + " x " + to_string(sideB) +
                   " mm, even stacked in layers up to " + to_string(a.maxH) + " mm";
    }
    return a;
}

CartonFit fitCarton(vector<Item> items, long long L, long long W, long long H) {
    sortLikeOptimizer(items);

    CartonFit fit;
    for (const auto& it : items) fit.sequence.push_back(it.id);

    // A: rows run along the carton length; rows stack up across the width.
    fit.attempts.push_back(tryOrientation(items, "rows_along_length", L, W, H));
    // B: rows run along the carton width; rows stack up along the length.
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

}  // namespace optimizer
