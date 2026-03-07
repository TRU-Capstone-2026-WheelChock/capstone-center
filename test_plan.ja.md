# Test Plan

このドキュメントは、`test/` 配下の現在の自動テスト coverage について、各テスト領域の目的と使用している mock 戦略をまとめたものです。

## 対象範囲

現在のテストスイートは主に以下を対象にしています。

- heartbeat の timeout と cleanup の挙動
- config の読み込みと起動時の配線
- message receive の dispatch
- processor 間の signal fan-out
- motor command の publish
- visual harness の HTTP handler の挙動

テストの中心は unit test で、一部に限定的な integration test を含みます。多くのテストでは実際の ZeroMQ socket を使わず、`msg_handler` の transport helper を in-memory の stand-in に置き換えています。

## テストファイル

### `test/test_heartBeat.py`

目的:

- `HeartbeatProcessor` における timeout、removal、cancellation の挙動を検証する

カバレッジ:

- timeout 後に component を dead として扱うこと
- remove threshold 超過後に heartbeat entry を削除すること
- loop parameter が正の値であることの検証
- watchdog loop からの cancellation が伝播すること
- 次回 watchdog 実行前に新しい heartbeat が来た場合に復帰できること

Mock の詳細:

- 外部 mock は使用していません
- 実際の `RuntimeState` と `HeartbeatProcessor` を使い、timestamp だけを人工的に調整しています

### `test/test_main.py`

目的:

- `src/capstone_center/main.py` の config 解析と起動時 helper の配線を検証する

カバレッジ:

- disk 上の YAML 読み込み
- subscriber option の構築
- 明示的 override 引数の適用
- 不正 config の reject
- display publisher option の構築
- motor publisher option の構築
- heartbeat config の抽出
- `CenterApp.run()` の task orchestration

Mock の詳細:

- `test_center_app_run_starts_recv_and_heartbeat` では各 processor の `run()` を `AsyncMock` に置き換えています
- それ以外のテストは in-memory の config dict と実際の `zmq.asyncio.Context` を使っています
- `test_load_config_reads_yaml` では file I/O を mock せず、一時ファイルを実際に作成しています

### `test/test_msg_recv_processor.py`

目的:

- `MessageRecvProcessor` の dispatch と error handling を検証する

カバレッジ:

- heartbeat が `_other_msg_handler` に dispatch されること
- sensor が `_sensor_msg_handler` に dispatch されること
- override が `_override_button` に dispatch されること
- 未知の message type を無視すること
- validation error 発生後も処理を継続すること
- assertion error 発生後も処理を継続すること
- override mode の state 更新
- subscriber options が subscriber factory に渡されること
- heartbeat に receiver 側時刻を使うこと

Mock の詳細:

- `msg_handler.get_async_subscriber` は in-memory async iterator を返す async context manager に置き換えています
- `msg_handler.SensorMessage.model_validate` は軽量な fake validator に置き換えています
- 一部のテストでは `msg_handler.GenericMessageDatatype` を patch しています
- dispatch 挙動を切り出すため、内部 handler を `AsyncMock` に差し替えているテストがあります
- `test_handle_heart_beat_uses_receiver_time_not_message_timestamp` では module-local の `datetime` provider を patch しています

### `test/test_signal_pipeline_integration.py`

目的:

- receive、sensor、display、motor の各 processing stage 間の限定的な integration を検証する

カバレッジ:

- sensor message が derived-state update まで伝播すること
- sensor processing から display / motor signal へ fan-out されること
- override が outbound display / motor message に伝播すること

Mock の詳細:

- subscriber input は in-memory async iterator で模擬しています
- publisher output は in-memory async publisher で模擬しています
- 必要に応じて `msg_handler.SensorPayload`、`DisplayMessage`、`MotorState`、`MotorMessage` を軽量 stand-in に置き換えています
- `CoalescedUpdateSignal`、`RuntimeState`、`DerivedState` は実オブジェクトを使っています

### `test/test_motor_sender_processor.py`

目的:

- event-driven な motor command 生成を検証する

カバレッジ:

- motor state decision logic
- motor signal が発火した時の message publish

Mock の詳細:

- `msg_handler.get_async_publisher` は in-memory async context manager に置き換えています
- `msg_handler.MotorState` は simple namespace に置き換えています
- `msg_handler.MotorMessage` は `SimpleNamespace` factory に置き換えています

### `test/test_motor_sender_periodic_retry.py`

目的:

- signal event が来ない時の `MotorSenderProcessor` の periodic resend 挙動を検証する

カバレッジ:

- timeout による periodic publish
- 期待した sender と folding command で繰り返し outbound message が送られること

Mock の詳細:

- `msg_handler.get_async_publisher` は in-memory async context manager に置き換えています
- `msg_handler.MotorState` は simple namespace に置き換えています
- `msg_handler.MotorMessage` は `SimpleNamespace` factory に置き換えています

### `test/test_visual_harness_api_smoke.py`

目的:

- 実サーバを起動せずに visual harness の HTTP handler を検証する

カバレッジ:

- POST `/api/sensors`
- GET `/api/state`
- shared state を介した handler 呼び出し間の状態保持

Mock の詳細:

- 実際の HTTP server は起動しません
- request / response stream には `io.BytesIO` を使っています
- handler object は `BaseHTTPRequestHandler` が必要とする最小限の method / field だけを手動で構築しています
- visual harness module は `importlib` で file から直接 import しています

## まだ十分にカバーできていない点

- 実際の ZeroMQ socket 相互接続
- `main()` を通した end-to-end 実行
- config に存在していても、まだ実装に配線されていない key に対する config-driven behavior
- display publisher の timing 挙動
  現状のテストは event-driven send と override propagation に寄っています
- Docker ベースの visual harness 起動

## 今後テストを足す時のメモ

- `presence.*`、`status.*`、`display.refresh_interval_sec` のような config key が有効化されたら、まず processor 単位でテストを追加するのが妥当です
- ZeroMQ 相互接続が重要になった場合は、unit test を複雑化するより専用の integration layer を追加した方がよいです
- transport 境界は mock しつつ、アプリケーション内部の state と processor logic は実物を動かす、という現在の方針は維持した方が扱いやすいです
