// 改行区切りの検証済みセンサーデータを標準入力から受け取り、0/1を出力する。
#include "landing_api.h"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
int main() {
    landing_reset();
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        double t = 0, a = 0, p = 0;
        char c1 = 0, c2 = 0;
        if (!(in >> t >> c1 >> a >> c2 >> p) || c1 != ',' || c2 != ',' ||
            !std::isfinite(t) || !std::isfinite(a) || !std::isfinite(p)) {
            std::cerr << "bad numeric input\n";
            return 2;
        }
        in >> std::ws;
        if (!in.eof()) { std::cerr << "unexpected input\n"; return 2; }
        int result = landing_step(t, a, p);
        if (result != 0 && result != 1) {
            std::cerr << "landing_step must return 0 or 1\n";
            return 3;
        }
        std::cout << result << '\n';
        if (!std::cout) return 4;
    }
    return 0;
}
