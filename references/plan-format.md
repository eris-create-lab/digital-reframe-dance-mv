# Edit Plan Format

Version 2.0の`direction.json`はAIディレクションとレンダリング計画を兼ねる。`render_reframe.py`は`shots`以下だけを実行し、入力動画の全フレームを隙間なく覆う。

```json
{
  "schema_version": "2.0",
  "style": "dance_mv",
  "direction_style": "IMPACT",
  "bpm": 128,
  "editing_concept": [
    "ビートと動作ピークに同期した短いリフレーム",
    "全身ショットを主役として維持"
  ],
  "timeline": [
    {"time": 0.0, "action": "full_body", "reason": "rest"},
    {"time": 1.3333, "action": "waist_up", "reason": "audio_peak@1.417s"}
  ],
  "grade": {
    "contrast": 1.04,
    "saturation": 1.06,
    "gamma": 0.99,
    "unsharp": 0.2
  },
  "recipe": {
    "concept": "IMPACT",
    "signature_techniques": ["tracking-punch-in", "short-flash"],
    "notes": "足の着地と手の横切りを優先"
  },
  "shots": [
    {
      "start_frame": 0,
      "end_frame": 40,
      "kind": "full"
    },
    {
      "start_frame": 40,
      "end_frame": 56,
      "kind": "waist",
      "crop": {"x": 80, "y": 25, "w": 560, "h": 980},
      "pan": {"x_end": 88, "y_end": 29},
      "zoom": {"start": 1.0, "end": 1.04},
      "transition": {"blur_frames": 2, "flash": 0.10, "rgb_shift": 2}
    },
    {
      "start_frame": 56,
      "end_frame": 361,
      "kind": "full"
    }
  ]
}
```

## フィールド

- `schema_version`: 計画形式。Version 2.0では`2.0`。
- `style`: 出力種別。現行は`dance_mv`。
- `direction_style`: CLEAN、IMPACT、GRAPHIC、FASHION、LIVEの基調。
- `bpm`: 音声解析値。音声がない場合は`null`。
- `editing_concept`: 人間が確認できる演出意図。
- `timeline`: 秒単位の演出要約。レンダリングの正本は`shots`。
- `start_frame`: 含む開始フレーム。
- `end_frame`: 含まない終了フレーム。
- `kind`: レシピ記録用。レンダリングには影響しない。
- `crop`: 元フレーム上の切り抜き。省略時は全画面。
- `pan`: ショット末尾のクロップ座標。省略時は固定。
- `zoom`: ショット内の追加ズーム。通常1.00〜1.06に抑える。
- `transition.blur_frames`: ショット頭だけに掛ける短いブラー。
- `transition.flash`: ショット頭の露光。通常0.05〜0.15。
- `transition.rgb_shift`: ショット頭のRGBずれピクセル数。通常1〜4。

## 制約

- 最初の`start_frame`を0にする。
- 前ショットの`end_frame`と次ショットの`start_frame`を一致させる。
- 最後の`end_frame`を入力動画の総フレーム数に一致させる。
- クロップを入力解像度内へ収める。
- 極端なアップを避け、目、手、靴、耳の切断をコンタクトシートで確認する。
- 秒数ではなくフレームで確定する。
