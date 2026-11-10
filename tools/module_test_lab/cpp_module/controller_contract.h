#ifndef CANSAT_CPP_MODULE_CONTRACT_H
#define CANSAT_CPP_MODULE_CONTRACT_H
// v8.2 PC-side C interface: return 1=許可, 0=拒否, -1=不正入力.
// ESP32-S3 / Arduino / CANドライバはこのヘッダーでは使用しません。
#ifdef __cplusplus
extern "C" {
#endif
int cansat_allow_command(int module, int command, int landed);
#ifdef __cplusplus
}
#endif

enum CanSatModule { CANSAT_MAIN=1, CANSAT_CAM=2, CANSAT_DRIVE=3 };
enum CanSatCommand { CANSAT_LANDING=1, CANSAT_MOVE=2, CANSAT_CAPTURE=3, CANSAT_STOP=4 };
#endif
