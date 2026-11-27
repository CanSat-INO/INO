# 初期整備前の調査記録

- 作業ブランチは feature/ino-firmware-foundation（47f94ad）。REGULUSのBoardConfigとIMU・気圧・磁気・I²Cスキャンの4試験に作業差分あり。
- cansat/main は仮入力・テレメトリのESP32サンプル。cansat/regulus_rtos はFreeRTOS共有データとセンサー個別試験。reference/regulus は旧実装のスナップショット。ローカルのREGULUS_mainもPlatformIOのひな形を持つ。
- tools/module_test_lab はPythonとPC向けC++で動作する既存試験基盤。個別モジュール、フェーズ、仮想バス、センサーログを扱う。
- 現ブランチに元からROS 2パッケージはなく、ローカルで確認できたorigin/feature/camera_simuにはino_camera_sim（Gazebo・ステレオ起動設定・評価ツール）がある。今後のROS 2結合はこれを再利用候補にする。
- ground_stationはnpm workspaces。ESP32 Arduino受信機、USBシリアル、WCPP、WebSocket、CSV、React/Vite表示を持つ。既存モードとフェーズは新しいINØ仕様に対応づけが必要。
- ルートREADME・機体README・Test Lab資料を確認。対象ブランチにルートAGENTS.mdと.github設定は当初なく、組織のローカル.githubに既存テンプレートあり。
- 参照元地上局のWCPPにはWASA Rocket ProjectのMIT形式通知がある。由来する箇所の通知を確認してから配布する。REGULUS参照コードのライセンス・公開範囲は未確認。新規外部ソースの取り込みは今回行っていない。
- 現チェックアウトで競技規則・正式審査書は特定できていない。20分、停止要件、自動Uplinkは正式資料確認待ち。
