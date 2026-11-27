# データ・座標・時刻

ROS REP-103/105を参考に機体X前・Y左・Z上、光学X右・Y下・Z前、局所ENU。map/odom/base_link、SI、ROS姿勢Quaternionを基本とし、UIのRPYや通信スケーリングは変換を記録する。

Mission/Module/Boot/Capture/Camera/Command/Path ID、Sequence、取得・受信時刻の採用範囲と型は共同設計。Main発行のCapture IDで左右画像とセンサーを対応付ける。再起動後の識別子重複を防ぎ、必要精度から同期方法を選ぶ。

有効性・品質、生値と処理値、エラーの発生元・重大度・復旧状態を記録する。INFO/WARNING/ERROR/CRITICALは分類候補。
