import os
import time
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import requests


def resolve_heygen_api_key(cli_api_key: Optional[str]) -> str:
    if cli_api_key:
        return cli_api_key.strip()
    env_key = os.getenv("HEYGEN_API_KEY")
    if env_key:
        return env_key.strip()
    raise RuntimeError(
        "Missing HeyGen API key. Provide via --heygen-api-key or env HEYGEN_API_KEY"
    )


def submit_heygen_generate(api_host: str, api_key: str, payload: Dict[str, Any]) -> str:
    url = f"{api_host.rstrip('/')}/v2/video/generate"
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    print(f"[debug] POST {url}")
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    body = resp.text
    print(f"[debug] status={resp.status_code} body={body[:500]}")
    if resp.status_code not in (200, 201, 202):
        raise RuntimeError(f"HeyGen submit failed: {resp.status_code} {body}")
    data = resp.json()
    video_id = (
        (data.get("data") or {}).get("video_id")
        or data.get("video_id")
        or data.get("id")
    )
    if not video_id:
        raise RuntimeError(f"Unexpected HeyGen response: {data}")
    return video_id


def poll_heygen_result(
    api_host: str,
    api_key: str,
    video_id: str,
    out_path: Path,
    poll_interval_sec: int = 8,
    max_wait_sec: int = 900,
) -> Path:
    status_url = f"{api_host.rstrip('/')}/v2/video/{video_id}"
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
    }
    start = time.time()
    while True:
        resp = requests.get(status_url, headers=headers, timeout=90)
        if resp.status_code != 200:
            raise RuntimeError(f"HeyGen status error: {resp.status_code} {resp.text}")
        body = resp.json()
        data = body.get("data") or body
        status = (data.get("status") or "").lower()
        if status in {"completed", "succeeded", "success", "done"}:
            video_url = data.get("video_url") or data.get("url") or data.get("download_url")
            if not video_url:
                raise RuntimeError(f"HeyGen completed but no video URL found: {body}")
            dl = requests.get(video_url, timeout=180)
            if dl.status_code != 200:
                raise RuntimeError(f"HeyGen download failed: {dl.status_code} {dl.text[:500]}")
            out_path.write_bytes(dl.content)
            return out_path
        if status in {"failed", "error"}:
            raise RuntimeError(f"HeyGen job failed: {body}")
        if time.time() - start > max_wait_sec:
            raise TimeoutError("Timed out waiting for HeyGen video result.")
        time.sleep(poll_interval_sec)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--heygen-api-key")
    parser.add_argument("--heygen-api-host", default=os.getenv("HEYGEN_API_HOST", "https://api.heygen.com"))

    # Required content
    parser.add_argument("--segment-text", required=True, help="Text to be spoken in the video")
    parser.add_argument("--heygen-voice-id", required=True, help="HeyGen voice id to use for speech")
    parser.add_argument("--avatar-id", required=True, help="HeyGen avatar_id to render")

    # Avatar options
    parser.add_argument("--avatar-style", default="normal")
    parser.add_argument("--avatar-scale", type=float, default=1.0)
    parser.add_argument("--talking-style", default="stable")
    parser.add_argument("--expression", default="default")

    # Voice options
    parser.add_argument("--emotion")
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--pitch", type=float, default=0.0)

    # Background and caption
    parser.add_argument("--background-type", default="image")
    parser.add_argument("--background-url", help="Public image URL for first background when type=image")
    parser.add_argument("--caption", action="store_true")

    # Overlay options (entry 2)
    parser.add_argument("--overlay-text")
    parser.add_argument("--overlay-font-family", default="Arial")
    parser.add_argument("--overlay-font-weight", default="bold")
    parser.add_argument("--overlay-color", default="#050404")
    parser.add_argument("--overlay-text-align", default="center")
    parser.add_argument("--overlay-font-size", type=float)
    parser.add_argument("--overlay-line-height", type=float)
    parser.add_argument("--overlay-pos-x", type=int, default=0)
    parser.add_argument("--overlay-pos-y", type=int, default=0)

    # Optional offsets for speaking avatar (entry 2)
    parser.add_argument("--char1-offset-x", type=int, default=0)
    parser.add_argument("--char1-offset-y", type=int, default=0)

    # Optional extras
    parser.add_argument("--folder-id")
    parser.add_argument("--callback-url")

    # Output
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--out-dir", default="outputs")

    args = parser.parse_args()

    api_key = resolve_heygen_api_key(args.heygen_api_key)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # video_inputs[0]: avatar shell + background (with image_url if provided)
    background0: Dict[str, Any] = {"type": args.background_type}
    if args.background_url and args.background_type == "image":
        background0["image_url"] = args.background_url
    character0: Dict[str, Any] = {
        "type": "avatar",
        "avatar": {
            "avatar_id": args.avatar_id,
            "scale": args.avatar_scale,
            "avatar_style": args.avatar_style,
        },
    }
    entry0: Dict[str, Any] = {
        "character": character0,
        "background": background0,
    }

    # video_inputs[1]: speaking avatar + voice + optional overlay text + background
    avatar1: Dict[str, Any] = {
        "avatar_id": args.avatar_id,
        "scale": args.avatar_scale,
        "avatar_style": args.avatar_style,
        "talking_style": args.talking_style,
        "expression": args.expression,
    }
    # Optional offset for entry 2
    if args.char1_offset_x or args.char1_offset_y:
        avatar1["offset"] = {"x": args.char1_offset_x, "y": args.char1_offset_y}

    character1: Dict[str, Any] = {
        "type": "avatar",
        "avatar": avatar1,
    }
    voice1: Dict[str, Any] = {
        "type": "text",
        "input_text": args.segment_text,
        "voice_id": args.heygen_voice_id,
        "locale": args.locale,
        "speed": args.speed,
        "pitch": args.pitch,
    }
    if args.emotion:
        voice1["emotion"] = args.emotion

    background1: Dict[str, Any] = {"type": args.background_type}

    entry1: Dict[str, Any] = {
        "character": character1,
        "voice": voice1,
        "background": background1,
    }

    if args.overlay_text:
        text_overlay: Dict[str, Any] = {
            "type": "text",
            "position": {"x": args.overlay_pos_x, "y": args.overlay_pos_y},
            "text": args.overlay_text,
            "font_family": args.overlay_font_family,
            "font_weight": args.overlay_font_weight,
            "color": args.overlay_color,
            "text_align": args.overlay_text_align,
        }
        if args.overlay_font_size is not None:
            text_overlay["font_size"] = args.overlay_font_size
        if args.overlay_line_height is not None:
            text_overlay["line_height"] = args.overlay_line_height
        entry1["text"] = text_overlay

    payload: Dict[str, Any] = {
        "caption": bool(args.caption),
        "dimension": {"width": args.width, "height": args.height},
        "video_inputs": [entry0, entry1],
    }

    if args.folder_id:
        payload["folder_id"] = args.folder_id
    if args.callback_url:
        payload["callback_url"] = args.callback_url

    print("[step] Submitting HeyGen video.generate job...")
    video_id = submit_heygen_generate(
        api_host=args.heygen_api_host,
        api_key=api_key,
        payload=payload,
    )
    print(f"[ok] Job submitted. video_id={video_id}")

    print("[step] Polling for HeyGen video result...")
    out_path = out_dir / f"video_{video_id}.mp4"
    final_path = poll_heygen_result(
        api_host=args.heygen_api_host,
        api_key=api_key,
        video_id=video_id,
        out_path=out_path,
    )
    print(f"[done] Video saved: {final_path}")


if __name__ == "__main__":
    main()
