# 地上局

WASAのローカル cansat-ground-station から必要なコードをコピーした構成。

- `frontend/`: React / Vite のCanSat CAD画面（全状態でCanSatを表示）
- `backend/`: USBシリアル受信、WCPP解析、WebSocket配信、CSVログ
- `shared/`: テレメトリ型・通信定数
- `receiver/receiver.ino`: ESP-NOW と USBシリアルを中継するESP32受信機

## 起動

このディレクトリで Node.js と npm を使って実行する。
Vite 8 の要件に合わせて Node.js 22.12以上を使用する。

```sh
npm ci
npm run dev
```

http://localhost:5173 を開く。バックエンドは既定で8080番ポート。
必要に応じてバックエンドの `SERIAL_PORT` と `WS_PORT`、画面側の `VITE_WS_URL` を設定する。
受信機スケッチはArduino用ESP32環境で書き込む。無線チャンネルはスケッチ内の `WIFI_CHANNEL` で確認する。

## 検証

```sh
npm run build --workspace=frontend
npx tsc --noEmit -p backend/tsconfig.json
```

## 現状

表示はCanSat CAD版を採用。元プロジェクトのミッション状態・操作コマンドは保持している。
INO機体との通信互換性、ピン設定、実機動作は未検証。INO専用化は今後の作業。
CSVログは実行時に `backend/logs/` に作成される。


WSL上のチェックアウトではWSL側のNode.js/npmで実行する。WindowsのnpmをUNCパスで実行するとworkspaceのリンク作成に失敗する場合がある。Windowsで使う場合はWindows側のローカルディレクトリに配置する。
