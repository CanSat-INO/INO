"""Rebuild the comparison report with tracking-loss checks and saved plots."""
import json
from pathlib import Path
from plot_run import plot
from design_config import ROOT

def report(path=None):
    path=Path(path or ROOT/'logs/design-comparison.json')
    summary=json.loads(path.read_text())
    lines=['# カメラ配置・合成草地の比較結果','',
           '合成画像・静的な草・簡易移動モデルでの短距離比較です。現地の再現精度や実機性能を保証しません。',
           '条件は各リンク先の requested.yaml を参照。乱数シード27の1試行ずつであり、最適設計を確定する試験ではありません。',
           '位置RMSEは初期姿勢のみ合わせたステレオオドメトリと真値の比較です。地図最適化後の精度ではありません。',
           '追跡継続の目安は、有効姿勢10件以上・初期化を含む有効率80%以上・最後の推定姿勢が3秒以内です。走行試験が終わっても、追跡が続いたとは限りません。',
           '', '| 条件 | SLAM追跡の目安 | 有効姿勢数 | 有効率（初期化含む） | 位置RMSE mm | 地面セル面積 m² | 最終姿勢の古さ s |',
           '|---|---|---:|---:|---:|---:|---:|']
    for row in summary:
        folder=ROOT/row['folder'];plot(folder)
        adequate=row['completed'] and row['matched_samples']>=10 and row['valid_fraction']>=.8 and row.get('final_pose_age_s') is not None and row['final_pose_age_s']<=3
        status='追跡継続' if adequate else '追跡不十分 / 要確認'
        error='—' if row['position_rmse_mm'] is None else f"{row['position_rmse_mm']:.2f}"
        age='—' if row['final_pose_age_s'] is None else f"{row['final_pose_age_s']:.2f}"
        lines.append(f"| [{row['case']}]({folder.name}/result.json)・[図]({folder.name}/overview.png) | {status} | {row['matched_samples']} | {row['valid_fraction']:.3f} | {error} | {row['ground_grid_m2']:.2f} | {age} |")
    lines+=['',
            '位置誤差が0に近くても、初期の静止姿勢しか得られていない場合は失敗です。サンプル数と最終姿勢の古さを優先して確認してください。',
            '地面セル面積は前方0〜3m・左右-2〜2mの固定領域で、地面近傍に点群があった10cmセルの面積です。地面復元の正確さや全域のマッピング成功率を表しません。',
            '低模様条件でもコーン・箱・マットは残っています。草だけの条件は grass_only の行を参照してください（実行した場合）。',
            '各フォルダに設定・左右画像・点群・軌跡・地図DB・ログ・実行時ソースを保存しています。',
            '入力機構: 調整したカメラで描画→平行化→停止/順次撮影選択→JPEG・遅延・欠落の模擬→RTAB-Map。真値は評価専用で、SLAMには入力しません。']
    path.with_suffix('.md').write_text('\n'.join(lines)+'\n')
    print(path.with_suffix('.md'))

if __name__=='__main__':report()
