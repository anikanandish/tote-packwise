#include <algorithm>
#include <cmath>
#include <ctime>
#include <iostream>
#include <limits>
#include <utility>
#include <vector>

using namespace std;

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
    long double score = numeric_limits<long double>::infinity();
    vector<Placement> p;
};

static Result pack(const vector<Item>& items, long long targetW) {
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

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    const clock_t start = clock();

    int n;
    if (!(cin >> n) || n < 1 || n > 10000) return 1;

    vector<Item> items(n);
    long long area = 0, maxSide = 0, total = 0;

    for (int i = 0; i < n; ++i) {
        if (!(cin >> items[i].l >> items[i].w >> items[i].h) ||
            items[i].l <= 0 || items[i].w <= 0 || items[i].h <= 0) {
            return 1;
        }

        items[i].id = i;
        area += items[i].l * items[i].w;
        maxSide = max(maxSide, min(items[i].l, items[i].w));
    }

    stable_sort(items.begin(), items.end(),
        [](const Item& a, const Item& b) {
            return max(a.l, a.w) > max(b.l, b.w);
        });

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

    if (best.p.empty()) return 2;

    cout << best.W << ' ' << best.L << ' ' << best.H << '\n';

    for (int i = 0; i < n; ++i) {
        const auto& p = best.p[i];
        cout << i << ' ' << p.x << ' ' << p.y << ' ' << p.z << ' '
             << p.l << ' ' << p.w << ' ' << p.h << ' '
             << (p.rotated ? 1 : 0) << '\n';
    }
}