#!/usr/bin/env python3
"""Ask Music Assistant to sync one provider after a rip (jmbrenot-infra fork).

Reads the add-on options ma_url, ma_token and ma_provider from /data/options.json.
Does nothing when ma_url or ma_token is empty. Never prints the token.
"""
import json
import sys
import urllib.error
import urllib.request

OPTIONS_FILE = "/data/options.json"


def main() -> int:
    try:
        with open(OPTIONS_FILE, encoding="utf-8") as f:
            options = json.load(f)
    except (OSError, ValueError) as err:
        print(f"[ARM] ma-sync: cannot read add-on options ({err})")
        return 1
    url = (options.get("ma_url") or "").rstrip("/")
    token = options.get("ma_token") or ""
    provider = options.get("ma_provider") or ""
    if not url or not token:
        print("[ARM] ma-sync: ma_url or ma_token not set, skipping")
        return 0
    args = {"providers": [provider]} if provider else {}
    payload = json.dumps({"command": "music/sync", "args": args, "message_id": "arm-rip"}).encode()
    request = urllib.request.Request(
        f"{url}/api",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        print(f"[ARM] ma-sync: Music Assistant refused the request (HTTP {err.code})")
        return 1
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"[ARM] ma-sync: Music Assistant unreachable ({err})")
        return 1
    try:
        result = json.loads(body)
    except ValueError:
        result = None
    # music/sync answers with the list of sync tasks it started; an unknown provider gives an empty list.
    if isinstance(result, dict) and "error_code" in result:
        print(f"[ARM] ma-sync: Music Assistant error {result.get('error_code')}: {result.get('details', '')}")
        return 1
    if not result:
        print(f"[ARM] ma-sync: no sync task started (check ma_provider: {provider!r})")
        return 1
    print(f"[ARM] ma-sync: {len(result)} sync task(s) started for {provider or 'all providers'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
