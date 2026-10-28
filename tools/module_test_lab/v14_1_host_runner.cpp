// Generic native host runner. Compile with exactly one CANSAT_TARGET_* macro.
// Receives 4 numeric arguments per line (unused values are 0). One int result/line.
#include "v14_1_contract.hpp"
#include <iostream>
#include <sstream>
#include <string>
int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream input(line);
        double a, b, c, d;
        std::string trailing;
        if (!(input >> a >> b >> c >> d) || (input >> trailing)) return 10;
        int output = -99;
#if defined(CANSAT_TARGET_LANDING)
        output = cansat_landing(a, b, static_cast<int>(c));
#elif defined(CANSAT_TARGET_DRIVE)
        output = cansat_drive(static_cast<int>(a), static_cast<int>(b), static_cast<int>(c), static_cast<int>(d));
#elif defined(CANSAT_TARGET_CAM)
        output = cansat_cam(static_cast<int>(a), b, c);
#elif defined(CANSAT_TARGET_MAIN)
        output = cansat_main(static_cast<int>(a), static_cast<int>(b), static_cast<int>(c), static_cast<int>(d));
#else
#error "Select CANSAT_TARGET_LANDING/DRIVE/CAM/MAIN"
#endif
        std::cout << output << '\n';
    }
    return 0;
}
