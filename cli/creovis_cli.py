"""CREOVIS CLI: clip long videos into vertical shorts from the terminal.

Zero dependencies by design so `uvx creovis` and `pipx run creovis`
start instantly. Talks to the same REST API the dashboard and the MCP server
use; nothing here can drift from what the app actually does.

Auth and target come from the environment:
  CREOVIS_API_KEY     osk_... key from the account page (cloud only)
                      (or legacy OPENSHORTS_API_KEY)
  CREOVIS_API_URL     defaults to https://api.creovis.app; set to
                      http://localhost:8000 for a self-hosted instance,
                      where no key is needed.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API = "https://api.creovis.app"
POLL_SECONDS = 10


def _base():
    return (os.environ.get("CREOVIS_API_URL") or os.environ.get("OPENSHORTS_API_URL") or DEFAULT_API).rstrip("/")


def _request(method, path, body=None):
    headers = {"Accept": "application/json"}
    key = os.environ.get("CREOVIS_API_KEY") or os.environ.get("OPENSHORTS_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_base() + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode() or "{}")
        except Exception:
            payload = {"detail": str(e.reason)}
        return e.code, payload
    except urllib.error.URLError as e:
        print(f"error: cannot reach {_base()} ({e.reason})", file=sys.stderr)
        sys.exit(2)


def _die(status, payload):
    detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
    if not isinstance(detail, str):
        detail = json.dumps(detail)
    print(f"error ({status}): {detail}", file=sys.stderr)
    sys.exit(1)


def cmd_quota(_args):
    status, payload = _request("GET", "/api/me")
    if status != 200:
        _die(status, payload)
    mins = payload.get("monthly_minutes")
    used = payload.get("minutes_used", 0)
    plan = payload.get("plan", "free")
    rem = "unlimited" if mins is None else max(0, mins - used)
    print(f"plan: {plan}")
    print(f"minutes: {rem} left ({used} used this period)")


def _poll(job_id, quiet=False):
    last = ""
    while True:
        status, payload = _request("GET", f"/api/status/{job_id}")
        if status != 200:
            _die(status, payload)
        state = payload.get("status")
        msg = payload.get("progress_message") or ""
        if not quiet and msg != last:
            if msg:
                print(f"… {msg}")
            last = msg
        if state == "completed":
            return payload
        if state == "failed":
            error = payload.get("error") or "processing failed"
            print(f"error: {error}", file=sys.stderr)
            sys.exit(1)
        time.sleep(POLL_SECONDS)


def cmd_process(args):
    body = {
        "url": args.url,
        "acknowledged": True,
        "captions": not args.no_captions,
        "auto_hook": not args.no_hook,
    }
    if args.preset:
        body["caption_preset"] = args.preset
    if args.webhook:
        body["webhook_url"] = args.webhook
    if args.webhook_secret:
        body["webhook_secret"] = args.webhook_secret
    if args.target_clips:
        body["target_clips"] = args.target_clips
    if args.low_quality:
        body["force_low_quality"] = True

    status, payload = _request("POST", "/api/process", body)
    if status == 409 and payload.get("detail") == "needs_confirmation":
        print(
            "warning: source video is low resolution. Pass --low-quality to proceed.",
            file=sys.stderr,
        )
        sys.exit(3)
    if status != 200:
        _die(status, payload)

    job_id = payload.get("job_id")
    print(f"job {job_id} started")
    if not args.wait:
        return

    result = _poll(job_id)
    clips = result.get("clips") or []
    print(f"done: {len(clips)} clips")
    for c in clips:
        idx = c.get("index")
        t = c.get("title", f"Clip {idx}")
        dur = c.get("duration_seconds")
        dstr = f" ({dur:.0f}s)" if dur else ""
        url = c.get("video_url") or c.get("download_url") or ""
        print(f"  [{idx}] {t}{dstr}\n      {url}")


def cmd_status(args):
    result = _poll(args.job_id, quiet=True) if args.wait else None
    if not result:
        status, result = _request("GET", f"/api/status/{args.job_id}")
        if status != 200:
            _die(status, result)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"status: {result.get('status')}")
    if result.get("progress_message"):
        print(f"progress: {result.get('progress_message')}")
    clips = result.get("clips") or []
    if clips:
        print(f"clips ({len(clips)}):")
        for c in clips:
            idx = c.get("index")
            t = c.get("title", f"Clip {idx}")
            print(f"  [{idx}] {t}: {c.get('video_url') or ''}")


def cmd_clips(args):
    status, payload = _request("GET", f"/api/status/{args.job_id}")
    if status != 200:
        _die(status, payload)
    clips = payload.get("clips") or []
    if args.json:
        print(json.dumps(clips, indent=2))
        return
    for c in clips:
        idx = c.get("index")
        t = c.get("title", f"Clip {idx}")
        dur = c.get("duration_seconds")
        dstr = f" ({dur:.0f}s)" if dur else ""
        print(f"[{idx}] {t}{dstr}")
        print(f"    url: {c.get('video_url') or ''}")
        if c.get("hook"):
            print(f"    hook: {c['hook']}")


def cmd_subtitles(args):
    body = {"job_id": args.job_id, "clip_index": args.clip_index, "preset": args.preset}
    status, payload = _request("POST", "/api/subtitle", body)
    if status != 200:
        _die(status, payload)
    print(f"rendered with {args.preset}: {payload.get('video_url')}")


def cmd_recut(args):
    body = {
        "job_id": args.job_id,
        "clip_index": args.clip_index,
        "start": args.start,
        "end": args.end,
    }
    status, payload = _request("POST", "/api/clip/rerender", body)
    if status != 200:
        _die(status, payload)
    print(f"recut ({args.start}s - {args.end}s): {payload.get('video_url')}")


def cmd_publish(args):
    body = {
        "job_id": args.job_id,
        "clip_index": args.clip_index,
        "platforms": [p.strip() for p in args.platforms.split(",")],
    }
    if args.title:
        body["title"] = args.title
    status, payload = _request("POST", "/api/social/post", body)
    if status != 200:
        _die(status, payload)
    print(f"published to {', '.join(body['platforms'])}")


def main():
    p = argparse.ArgumentParser(
        prog="creovis",
        description="Clip long videos into vertical shorts from the terminal.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("quota", help="Show remaining processing minutes and plan")

    p_proc = sub.add_parser("process", help="Start clipping a video from its URL")
    p_proc.add_argument("url", help="YouTube URL or direct video file URL")
    p_proc.add_argument("--no-captions", action="store_true", help="Skip subtitles")
    p_proc.add_argument("--no-hook", action="store_true", help="Skip the AI hook line")
    p_proc.add_argument("--preset", help="Subtitle style (e.g. hormozi, devin, bold_stroke)")
    p_proc.add_argument("--target-clips", type=int, help="Target number of clips (1-15)")
    p_proc.add_argument("--webhook", help="URL to POST when processing completes")
    p_proc.add_argument("--webhook-secret", help="Secret for HMAC-SHA256 X-Creovis-Signature")
    p_proc.add_argument("--low-quality", action="store_true", help="Force proceed if source is low-res")
    p_proc.add_argument("--wait", action="store_true", help="Poll until done and print clip URLs")
    p_proc.set_defaults(func=cmd_process)

    p_stat = sub.add_parser("status", help="Check progress or fetch finished clips")
    p_stat.add_argument("job_id", help="Job ID returned by process")
    p_stat.add_argument("--wait", action="store_true", help="Wait until completed or failed")
    p_stat.add_argument("--json", action="store_true", help="Raw JSON output")
    p_stat.set_defaults(func=cmd_status)

    p_clips = sub.add_parser("clips", help="List finished clips for a job")
    p_clips.add_argument("job_id", help="Job ID")
    p_clips.add_argument("--json", action="store_true", help="Raw JSON output")
    p_clips.set_defaults(func=cmd_clips)

    p_sub = sub.add_parser("subtitles", help="Re-burn a clip with a different subtitle preset")
    p_sub.add_argument("job_id")
    p_sub.add_argument("clip_index", type=int)
    p_sub.add_argument("preset", help="hormozi, devin, beast, minimal, bold_stroke, clean, neon, typewriter")
    p_sub.set_defaults(func=cmd_subtitles)

    p_recut = sub.add_parser("recut", help="Re-trim a clip to new start/end timestamps")
    p_recut.add_argument("job_id")
    p_recut.add_argument("clip_index", type=int)
    p_recut.add_argument("--start", type=float, required=True, help="New start time in seconds")
    p_recut.add_argument("--end", type=float, required=True, help="New end time in seconds")
    p_recut.set_defaults(func=cmd_recut)

    p_pub = sub.add_parser("publish", help="Publish a clip to connected social accounts")
    p_pub.add_argument("job_id")
    p_pub.add_argument("clip_index", type=int)
    p_pub.add_argument("--platforms", default="tiktok,instagram,youtube",
                       help="Comma-separated: tiktok,instagram,youtube,facebook,linkedin,threads,bluesky")
    p_pub.add_argument("--title", help="Post caption (defaults to clip title)")
    p_pub.set_defaults(func=cmd_publish)

    args = p.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    elif args.cmd == "quota":
        cmd_quota(args)


if __name__ == "__main__":
    main()
