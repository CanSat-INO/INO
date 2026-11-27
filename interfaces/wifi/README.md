# Wi-Fi画像転送（共同設計）

Cameraから左右静止画を送る。Capture IDとCamera IDを保持し、撮影・保持・受信の結果を区別する。欠損、再送、再接続、バッファ満杯を扱う。HTTP/TCP/WebSocket、圧縮、画質、解像度は計測で選ぶ。
