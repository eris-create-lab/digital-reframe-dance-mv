---
name: digital-reframe-dance-mv
description: Automatically transform an uploaded single-camera dance MP4 into a polished multi-shot-style MV by analyzing video and music, directing the edit, generating a JSON plan, rendering digital reframes and tracking, and validating the final MP4 while preserving character identity, choreography, timeline, and audio sync. Use for requests such as MP4を投げるだけでMV化, ワンカット動画を自動編集, ダンス動画へ顔・腰上・バストアップを追加, 固定カメラ映像を複数カメラ風に編集, or creating an original-vs-edited comparison video.
---

# Digital Reframe Dance MV

## 目的

MP4を受け取ったら、解析、AIディレクション、JSON計画、編集、検証まで自動で完了する。存在しない映像を生成せず、素材から演出方針を決める。ユーザーへ編集操作や設定を求めない。

## 絶対条件

- キャラクター、顔、衣装、ポーズ、振付を描き直さない。
- 元カメラから見えない角度や背景を生成しない。
- 明示許可がない限り、時間軸、再生速度、フレーム順を変更しない。
- 音声差し替えの指定がなければ、元音声ストリームを維持する。
- 全身ショットを基本とし、アップをアクセントとして使う。
- 残像を標準効果にしない。アニメ動画では輪郭破綻に見えやすい。
- 派手さより同一性、モーション、同期を優先する。

## ワークフロー

1. 入力MP4ごとに作業ディレクトリを用意する。
2. `scripts/direct_video.py INPUT.mp4 OUTPUT.mp4 --work-dir WORK` を実行する。
3. `analysis.json` で解像度、FPS、尺、シーン変化、動き、被写体追跡、BPM、ビート、音量ピーク、サビ候補を確認する。
4. `direction.json` で素材根拠、演出方針、タイムライン、クロップが妥当か確認する。詳しい形式は [plan-format.md](references/plan-format.md) を読む。
5. 自動生成された`contact.jpg`を見て、顔・手・靴の切断を視覚確認する。危険なアップは全身か腰上へ戻して再レンダリングする。
6. `validation.json` の全項目が真であることを確認し、完成MP4を返す。不一致を残したまま納品しない。

`direct_video.py` は次を順番に実行する。

- `analyze_video.py`: モデル不要の映像・音声解析と被写体追跡。
- `generate_edit_plan.py`: 解析根拠からVersion 2.5演出JSONを生成。
- `render_reframe.py`: JSONだけを見てフレーム精度で編集。
- `validate_output.py`: 解像度、FPS、総フレーム数、尺、音声を照合。

ユーザーが演出を指定した場合だけ `direction.json` を調整する。指定がなければ自動案で最後まで進める。

Version 2.5ではVersion 2.1のリフレーム、カメラ、ビート同期、Camera Shake、Flash、Exposure、Motion Blur、Speed Rampを元の控えめな強度で維持し、RGB Glitch、Color Grade、Accent Color、Bloom、Light Leakを追加する。色と光は仕上げとして薄く使い、単体の効果へ視線を奪わせない。強いピークへ効果を分散し、同じ瞬間へ全部を重ねない。Speed Rampは区間内で加減速を相殺し、ショット終端で元の時間軸へ戻す。

## 編集判断

- 10〜20秒では全身を概ね70〜85％維持する。
- アップは通常3〜4回、各0.5〜0.8秒から検討する。素材が元から寄る場合は減らす。
- カット位置を時刻の等分で決めず、動作の開始、頂点、着地、視線、手足の横切りに合わせる。
- 顔、腰上、胸元、足元、手元から、実際に意味がある箇所だけを選ぶ。
- エフェクトを全画面へ常時掛けず、動作のアクセント前後2〜6フレームへ限定する。
- Camera Shakeは最大12px、Motion Blurは最大4フレームに制限する。
- RGB Glitchは最大2px・2フレーム、BloomとLight Leakは最大6フレームに制限する。
- 視覚レビューでは、色・光・グリッチがダンスやキャラクターより先に目へ入らないことを確認する。
- Speed Rampは1区間だけを原則とし、総フレーム数、総尺、音声同期を変えない。
- マスク合成では人物を鮮明に保ち、背景側へブラー、暗転、ライトスイープを適用する。
- 仕上がりが騒がしい場合は、効果を弱める前にカット数を減らす。

## 変化を作る

- CLEAN、IMPACT、GRAPHIC、FASHION、LIVEから素材に合う基調を選ぶ。
- 同じ動画内で複数の基調を混ぜすぎない。
- 前回使った「顔→足→胸→手」の順番や同じタイムコード比率を流用しない。
- 毎回、選んだ基調、シグネチャー技法、カット構成を編集レシピとして短く記録する。
- 再実行時は編集レシピを変え、ランダムではなく素材根拠のある別案を作る。

## レビュー基準

- 元映像とフレームを照合し、別人化や動作変更がないことを確認する。
- アップが頭、手、靴を不自然に切っていないことを確認する。
- カット前後の視線移動が成立していることを確認する。
- 音声がある場合、編集後も同期がずれていないことを確認する。
- 技法が目立つだけでダンスを見づらくしていないことを確認する。

## 付属スクリプト

- `direct_video.py`: MP4入力から検証済みMP4出力までを一気通貫で実行する。
- `analyze_video.py`: 映像、動き、被写体位置、BPM、ビート、ピーク、サビ候補を解析する。
- `generate_edit_plan.py`: 解析JSONからAIディレクションと編集計画を生成する。
- `probe_video.py`: 素材確認用メタデータ、コンタクトシート、波形を生成する。
- `render_reframe.py`: JSONプランからフレーム精度でデジタルリフレーミングする。
- `validate_output.py`: 元動画と編集版の技術的一致を検証する。
- `make_comparison.py`: 左右並列で元動画→停止→編集版→停止の比較動画を作る。
