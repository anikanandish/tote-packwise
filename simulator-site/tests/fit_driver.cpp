// Prints fitCarton() results for the equivalence test. Input: L W H n, then n lines "l w h".
#include <iostream>
#include "packer_core.hpp"
int main() {
    long long L, W, H; int n;
    while (std::cin >> L >> W >> H >> n) {
        std::vector<packer::Item> items(n);
        for (int i = 0; i < n; ++i) { std::cin >> items[i].l >> items[i].w >> items[i].h; items[i].id = i; }
        auto f = packer::fitCarton(items, L, W, H);
        if (!f.fits) { std::cout << "nofit\n"; continue; }
        const auto& a = f.attempts[f.chosen];
        std::cout << a.orientation << ' ' << a.result.W << ' ' << a.result.L << ' ' << a.result.H;
        for (int i = 0; i < n; ++i) { const auto& p = a.result.p[i]; std::cout << ' ' << p.x << ',' << p.y << ',' << p.l << ',' << p.w << ',' << p.rotated; }
        std::cout << '\n';
    }
}
