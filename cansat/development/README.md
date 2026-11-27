# 機体モジュールの開発用ひな形

PC上でビルドするC++ひな形。実装を始めるときは担当者が実際の入力と出力の型を設計し、暫定宣言を差し替える。機体共通の型は interfaces で合意する。

- Main: include/MainScaffold.h。既存の cansat/main と cansat/regulus_rtos を参照。
- Camera: include/CameraScaffold.h。単眼取得、転送、CAN、左右組を順に検証。
- Drive: include/DriveScaffold.h。出力なしの指令検証から開始。
- tests/: 各対象の未実装状態をPCで確認する。マイコンの基板・SDK・ピンはハード仕様確定後に選ぶ。

```sh
cmake -S cansat/development -B /tmp/ino-dev-build
cmake --build /tmp/ino-dev-build
ctest --test-dir /tmp/ino-dev-build --output-on-failure
```
