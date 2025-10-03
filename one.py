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

# --- HeyGen integration ---


def submit_heygen_generate(
    api_host: str,
    api_key: str,
    payload: Dict[str, Any],
) -> str:
    """Submit a video generation job to HeyGen v2 with provided payload.

    Returns a `video_id` for polling.
    """
    url = f"{api_host.rstrip('/')}/v2/video/generate"
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    print(f"[debug] POST {url}")
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"[debug] status={resp.status_code} body={resp.text[:500]}")
    if resp.status_code not in (200, 201, 202):
        raise RuntimeError(
            "HeyGen submit failed: "
            f"{resp.status_code} {resp.text[:500]}"
        )
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
    """Poll HeyGen v2 video status, download when ready."""
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
            # Download the video bytes
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
    # HeyGen only
    parser.add_argument("--heygen-api-key")
    parser.add_argument("--heygen-api-host", default=os.getenv("HEYGEN_API_HOST", "https://api.heygen.com"))

    # Core content
    parser.add_argument("--segment-text", required=True, help="Text to be spoken in the video")
    parser.add_argument("--heygen-voice-id", required=True, help="HeyGen voice id to use for speech")

    # Avatar character options
    parser.add_argument("--avatar-id", required=True, help="HeyGen avatar_id to render")
    parser.add_argument("--avatar-style", default="normal")
    parser.add_argument("--avatar-scale", type=float, default=1.0)
    parser.add_argument("--talking-style", default="stable")
    parser.add_argument("--expression", default="default")

    # Voice options
    parser.add_argument("--emotion", help="Voice emotion tag")
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--pitch", type=float, default=0.0)

    # Background and caption
    parser.add_argument("--background-type", default="image")
    parser.add_argument("--background-url", help="Public image URL to use as background when type=image")
    parser.add_argument("--caption", action="store_true", help="Enable auto captions")

    # Optional overlay text
    parser.add_argument("--overlay-text", help="Optional overlay text content")
    parser.add_argument("--overlay-font-family", default="Arial")
    parser.add_argument("--overlay-font-weight", default="bold")
    parser.add_argument("--overlay-color", default="#050404")
    parser.add_argument("--overlay-text-align", default="center")
    parser.add_argument("--overlay-font-size", type=float)
    parser.add_argument("--overlay-line-height", type=float)

    # Dimensions and output
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--out-dir", default="outputs")

    args = parser.parse_args()

    # Resolve HeyGen key
    heygen_api_key = resolve_heygen_api_key(args.heygen_api_key)

    width, height = args.width, args.height

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build payload aligned with provided sample (single speaking avatar entry)
    video_inputs = []

    # Speaking avatar with voice
    character_obj: Dict[str, Any] = {
        "type": "avatar",
        "avatar": {
            "avatar_id": args.avatar_id,
            "scale": args.avatar_scale,
            "avatar_style": args.avatar_style,
            "talking_style": args.talking_style,
            "expression": args.expression,
        },
    }
    voice_obj: Dict[str, Any] = {
        "type": "text",
        "input_text": args.segment_text,
        "voice_id": args.heygen_voice_id,
        "locale": args.locale,
        "speed": args.speed,
        "pitch": args.pitch,
    }
    if args.emotion:
        voice_obj["emotion"] = args.emotion

    background_two: Dict[str, Any] = {"type": args.background_type}
    if args.background_url and args.background_type == "image":
        background_two["image_url"] = args.background_url
    entry_two: Dict[str, Any] = {
        "character": character_obj,
        "voice": voice_obj,
        "background": background_two,
    }

    if args.overlay_text:
        text_overlay: Dict[str, Any] = {
            "type": "text",
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
        entry_two["text"] = text_overlay

    video_inputs.append(entry_two)

    payload: Dict[str, Any] = {
        "caption": bool(args.caption),
        "dimension": {"width": width, "height": height},
        "video_inputs": video_inputs,
    }

    print("[step] Submitting HeyGen video.generate job...")
    video_id = submit_heygen_generate(
        api_host=args.heygen_api_host,
        api_key=heygen_api_key,
        payload=payload,
    )
    print(f"[ok] Job submitted. video_id={video_id}")

    print("[step] Polling for HeyGen video result...")
    video_path = out_dir / f"video_{video_id}.mp4"
    final_path = poll_heygen_result(
        api_host=args.heygen_api_host,
        api_key=heygen_api_key,
        video_id=video_id,
        out_path=video_path,
    )
    print(f"[done] Video saved: {final_path}")


if __name__ == "__main__":
    main()
