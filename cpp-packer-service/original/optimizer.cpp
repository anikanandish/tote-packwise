#include <algorithm>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <limits>
#include <utility>
#include <vector>

using namespace std;

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
    long double score = numeric_limits<long double>::infinity();
    vector<Placement> p;
    bool success = false;
};

static Result pack3D(const vector<Item>& items, long long targetW,
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

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    const clock_t start_time = clock();

    int n;
    if (!(cin >> n) || n < 1 || n > 10000) return 1;

    vector<Item> items(n);

    for (int i = 0; i < n; ++i) {
        if (!(cin >> items[i].l >> items[i].w >> items[i].h) ||
            items[i].l <= 0 || items[i].w <= 0 || items[i].h <= 0) {
            return 1;
        }

        int c;
        while ((c = cin.peek()) == ' ' || c == '\t' || c == '\r') cin.get();
        if (c == '0' || c == '1') {
            int f;
            cin >> f;
            items[i].fragile = (f == 1);
        }

        items[i].id = i;
    }

    long long lo = 1, hiDim = 0;
    for (const auto& it : items) {
        long long pad = it.fragile ? CUSHION_TOTAL : 0;
        long long pl = it.l + pad, pw = it.w + pad, ph = it.h + pad;
        if (ph > MAX_H) return 3;
        lo = max(lo, min(pl, pw));
        hiDim += max(pl, pw);
    }
    hiDim = max(hiDim, lo);

    stable_sort(items.begin(), items.end(), [](const Item& a, const Item& b) {
        return (a.l * a.w) > (b.l * b.w);
    });

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

    if (!best_result.success || best_result.p.empty()) return 2;

    cout << best_result.W << ' ' << best_result.L << ' ' << best_result.H << '\n';

    cout << fixed << setprecision(1);
    for (int i = 0; i < n; ++i) {
        const auto& p = best_result.p[i];
        cout << i << ' ' << p.x << ' ' << p.y << ' ' << p.z << ' '
             << p.l << ' ' << p.w << ' ' << p.h << ' '
             << (p.rotated ? 1 : 0) << '\n';
    }
    return 0;
}
