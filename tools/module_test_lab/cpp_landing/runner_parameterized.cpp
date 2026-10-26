// v7 only: trusted host-side C++ detector exposing landing_configure().
#include "landing_api.h"
#include <cmath>
#include <cerrno>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
extern "C" void landing_configure(double impact_threshold_mps2, double stable_hold_ms);
static bool read_number(const char* s, double& n) {
    errno = 0;
    char* end = nullptr;
    n = std::strtod(s, &end);
    return s != end && *end == '\0' && errno == 0 && std::isfinite(n);
}
int main(int argc, char** argv) {
    double threshold=0.0, hold=0.0;
    if (argc != 3 || !read_number(argv[1], threshold) || !read_number(argv[2], hold) ||
        threshold < 1.0 || threshold > 100.0 || hold < 0.0 || hold > 5000.0) {
        std::cerr << "invalid tuning parameters\n"; return 2;
    }
    landing_configure(threshold, hold);
    landing_reset();
    std::string line;
    while (std::getline(std::cin,line)) {
        std::istringstream in(line);
        double t=0,a=0,p=0;
        char c1=0,c2=0;
        if (!(in >> t >> c1 >> a >> c2 >> p) || c1!=',' || c2!=',' ||
            !std::isfinite(t) || !std::isfinite(a) || !std::isfinite(p)) {
            std::cerr << "bad numeric input\n"; return 3;
        }
        in >> std::ws;
        if (!in.eof()) { std::cerr << "unexpected input\n"; return 3; }
        int r=landing_step(t,a,p);
        if (r!=0 && r!=1) { std::cerr << "landing_step must return 0 or 1\n"; return 4; }
        std::cout << r << '\n';
        if (!std::cout) return 5;
    }
    return 0;
}
