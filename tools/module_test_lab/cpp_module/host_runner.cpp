// Protocol: one line: module command landed (integers), one line response: 1/0/-1.
// No input is executed as code. User-provided C++ file is compiled separately.
#include "controller_contract.h"
#include <iostream>
int main() {
    int mod, cmd, landed;
    while (std::cin >> mod >> cmd >> landed) {
        int result = cansat_allow_command(mod, cmd, landed);
        std::cout << result << '\n';
    }
    if (!std::cin.eof()) return 2;
    return 0;
}
