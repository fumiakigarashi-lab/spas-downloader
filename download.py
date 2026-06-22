"""
SPAS PDF ダウンローダー（GitHub Actions用）
更新チェック・リトライ付き
"""

import requests
import time
import sys
import os
from pathlib import Path

URL        = "https://www.hbc.co.jp/tecweather/SPAS.pdf"
META_FILE  = Path("last_meta.txt")   # リポジトリに保存されるメタ情報
MAX_RETRIES = 3     # 通信エラー時のリトライ回数
RETRY_WAIT  = 15    # 秒（通信エラー時のみ短く待機）


def load_meta() -> dict:
    if not META_FILE.exists():
        return {}
    return dict(
        line.split("=", 1)
        for line in META_FILE.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def save_meta(meta: dict) -> None:
    META_FILE.write_text(
        "\n".join(f"{k}={v}" for k, v in meta.items() if v),
        encoding="utf-8",
    )


def is_updated(current: dict, previous: dict) -> bool:
    if not previous:
        return True
    for key in ("etag", "last_modified"):
        if current.get(key) and previous.get(key):
            return current[key] != previous[key]
    return True  # ヘッダなし → 常にダウンロード


# 環境変数 JST_TIME はワークフローで設定される (例: 20260602_0525)
timestamp    = os.environ.get("JST_TIME", "unknown")
filename     = f"SPAS_{timestamp}.pdf"
previous     = load_meta()
skip_check   = os.environ.get("SKIP_UPDATE_CHECK", "false").lower() == "true"

print(f"=== ダウンロード開始: {timestamp} ===")
if skip_check:
    print("手動実行のため更新チェックをスキップします")

for attempt in range(1, MAX_RETRIES + 1):
    print(f"試行 {attempt}/{MAX_RETRIES}")
    try:
        r = requests.head(URL, timeout=30)
        r.raise_for_status()
        current = {
            "last_modified": r.headers.get("Last-Modified"),
            "etag":          r.headers.get("ETag"),
        }

        if not skip_check and not is_updated(current, previous):
            # まだ更新されていない場合は待たずに終了する。
            # 1日複数回（cron + GASトリガー）実行されるため、
            # 次回以降の実行で最新版を確実に取得できる。
            print(f"未更新のため終了します (Last-Modified: {current.get('last_modified')})")
            sys.exit(0)

        r2 = requests.get(URL, timeout=30)
        r2.raise_for_status()
        Path(filename).write_bytes(r2.content)
        save_meta(current)
        print(f"保存完了: {filename} ({len(r2.content):,} bytes)")
        sys.exit(0)

    except requests.RequestException as e:
        # 通信エラーは一時的な不調のことが多いので、短い間隔で数回だけ再試行する
        print(f"通信エラー: {e}")
        if attempt < MAX_RETRIES:
            print(f"{RETRY_WAIT} 秒後に再試行します...")
            time.sleep(RETRY_WAIT)

print("全試行が失敗しました。")
sys.exit(1)
