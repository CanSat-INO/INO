// Host example: stdin is a single role-specific request. Output is one action.
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::string role = argv[1];
    if (role == "main") {
        std::string imu;
        if (std::getline(std::cin, imu)) std::cout << "capture\n";
    } else if (role == "camera") {
        std::string left, right;
        if (!std::getline(std::cin, left) || !std::getline(std::cin, right)) return 2;
        if (!std::ifstream(left, std::ios::binary) || !std::ifstream(right, std::ios::binary)) return 3;
        std::cout << "retain\n";
    } else if (role == "drive") {
        double forward, turn;
        if (!(std::cin >> forward >> turn)) return 2;
        std::cout << std::setprecision(17) << forward << ' ' << turn << '\n';
    } else {
        return 2;
    }
}
