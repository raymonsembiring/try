import os
import time
import base64
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import requests
import mimetypes


def resolve_heygen_api_key(cli_api_key: Optional[str]) -> str:
    if cli_api_key:
        return cli_api_key.strip()
    env_key = os.getenv("HEYGEN_API_KEY")
    if env_key:
        return env_key.strip()
    raise RuntimeError(
        "Missing HeyGen API key. Provide via --heygen-api-key or env HEYGEN_API_KEY"
    )

def _guess_mime_type_from_path(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    return "image/png"


def _build_data_url(image_bytes: bytes, mime_type: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


# --- HeyGen integration ---


def submit_heygen_generate(
    api_host: str,
    api_key: str,
    image_source: str,
    script_text: str,
    voice_id: str,
    width: int,
    height: int,
) -> str:
    """Submit a video generation job to HeyGen v2 using an image talking photo.

    `image_source` should be either a public URL or a data URL (data:image/*;base64,...).
    Returns a `video_id` for polling.
    """
    url = f"{api_host.rstrip('/')}/v2/video/generate"
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "video_inputs": [
            {
                "character": {
                    "type": "image",
                    "image_url": image_source,
                },
                "voice": {
                    "voice_id": voice_id,
                    "input_text": script_text,
                },
            }
        ],
        "dimension": {"width": width, "height": height},
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
    parser.add_argument("--heygen-voice-id", required=True, help="HeyGen voice id to use for speech")
    parser.add_argument("--segment-text", required=True, help="Text to be spoken in the video")
    parser.add_argument("--image-path", help="Local path to the talking photo image")
    parser.add_argument("--image-url", help="Public URL to the talking photo image")

    # Optional dimensions and output
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--out-dir", default="outputs")

    args = parser.parse_args()

    # Resolve HeyGen key
    heygen_api_key = resolve_heygen_api_key(args.heygen_api_key)

    if not args.image_path and not args.image_url:
        raise RuntimeError("Provide either --image-path or --image-url for the talking photo")

    # Build image source (prefer URL if both provided)
    if args.image_url:
        image_source = args.image_url.strip()
    else:
        image_path = Path(args.image_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        mime = _guess_mime_type_from_path(image_path)
        image_bytes = image_path.read_bytes()
        image_source = _build_data_url(image_bytes, mime)

    width, height = args.width, args.height

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[step] Submitting HeyGen video.generate job...")
    video_id = submit_heygen_generate(
        api_host=args.heygen_api_host,
        api_key=heygen_api_key,
        image_source=image_source,
        script_text=args.segment_text,
        voice_id=args.heygen_voice_id,
        width=width,
        height=height,
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
