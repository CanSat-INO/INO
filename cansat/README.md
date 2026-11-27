# 機体ファームウェア

- [main](main) は仮入力で動作確認するESP32の例。
- [regulus_rtos](regulus_rtos) はREGULUS基板向けのFreeRTOSひな形とセンサーの単体試験。
- [development](development/README.md) はMain・Camera・DriveのPC用ひな形とビルド手順。
- [過去のREGULUSコード](../reference/regulus)は参照用。INOの基板仕様はハード班と確認する。

機体の通常開発は PlatformIO。VS Codeで担当先の main、camera、drive を個別に開くか、リポジトリルートから実行する。

```sh
pio run -d cansat/main
pio run -d cansat/camera
pio run -d cansat/drive
```

Camera・DriveのESP32-S3環境はコンパイル確認用。実機の基板、ピン、機構の仕様は別途決める。
CMakeの development はPC向け試験用。将来、機体とシミュレーターで共有する純粋C++を追加する場合は、両環境から同じソースをコンパイルする。
