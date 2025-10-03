import os
import io
import time
import base64
import argparse
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import requests


ALLOWED_SDXL_DIMS: List[Tuple[int, int]] = [
    (1024, 1024),
    (1152, 896),
    (1216, 832),
    (1344, 768),
    (1536, 640),
    (896, 1152),
    (832, 1216),
    (768, 1344),
    (640, 1536),
]


def resolve_api_key(cli_api_key: Optional[str]) -> str:
    if cli_api_key:
        return cli_api_key.strip()
    env_key = os.getenv("STABILITY_API_KEY")
    if env_key:
        return env_key.strip()
    for path in [
        Path.home() / ".config" / "stabilityai" / "api_key",
        Path.home() / ".stabilityai.key",
    ]:
        try:
            if path.is_file():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    return content
        except Exception:
            pass
    raise RuntimeError(
        "Missing API key. Provide via --api-key, env STABILITY_API_KEY, or ~/.config/stabilityai/api_key"
    )


def resolve_heygen_api_key(cli_api_key: Optional[str]) -> str:
    if cli_api_key:
        return cli_api_key.strip()
    env_key = os.getenv("HEYGEN_API_KEY")
    if env_key:
        return env_key.strip()
    raise RuntimeError(
        "Missing HeyGen API key. Provide via --heygen-api-key or env HEYGEN_API_KEY"
    )


def snap_sdxl_dims(requested_w: int, requested_h: int) -> Tuple[int, int]:
    target_ar = requested_w / requested_h
    target_area = requested_w * requested_h

    def score(wh: Tuple[int, int]) -> Tuple[float, int]:
        w, h = wh
        return (abs((w / h) - target_ar), abs((w * h) - target_area))

    return min(ALLOWED_SDXL_DIMS, key=score)


def build_prompt(character_key: str, identity_descriptor: str, company_name: str, segment_text: str) -> str:
    id_lock = (
        "This video MUST feature the SAME person across all segments. "
        f"Character Key: {character_key}. "
        f"Identity description: {identity_descriptor}. "
        "Age strictly in the fifties (50–59). Do NOT depict ages 20–40. "
        "Skin tone/color must remain EXACTLY the same across all segments; do NOT lighten, darken, desaturate, or change hue. "
        "Do NOT change identity, gender, age, hair style/color, facial hair, clothing, or background across segments."
    )
    bg_lock = (
        f'Fixed professional corporate office environment of "{company_name}". '
        "Locked-off tripod shot with identical camera position, angle, focal length, framing, subject distance, and crop for every segment. "
        "Same decor and background arrangement (glass walls, modern office), consistent neutral brand color palette, and IDENTICAL lighting and white balance to preserve skin tone. "
        "No camera movement (no pan, no tilt, no zoom, no dolly), no parallax, no reframing, no crop changes, no background element movement, no lighting and white-balance changes."
    )
    return (
        f"Cinematic portrait of a real person. {id_lock} {bg_lock} "
        'Close-up head and shoulders, looking at camera, speaking slowly (±110 WPM) with ~300ms pauses at commas and ~700ms at sentence ends, '
        f'saying: "{segment_text}". Soft natural studio lighting, realistic skin tones, detailed skin texture, sharp eyes, shallow depth of field, '
        "smooth bokeh, 4K, natural expression, live-action, documentary, interview framing, natural lip sync."
    )


NEGATIVE_PROMPT = (
    "identity change, different person, mismatched face, face morphing, "
    "young-looking, baby face, youthful appearance, twenties, thirties, 20s, 30s, 20-40 years old, "
    "skin tone change, skin color change, lighter skin, darker skin, pale, tanned, "
    "color cast, white balance shift, hue shift, saturation shift, exposure shift, contrast shift, "
    "background change, camera movement, pan, tilt, zoom, dolly, push-in, parallax, reframe, crop change, angle change, focal length change, "
    "lighting change, decor moved, brand color shift, "
    "low quality, cartoon, anime, cgi, avatar, blur, pixelation, oversharpen, uncanny, waxy skin, "
    "watermark, logo, on-screen text, fast-talking, rapid speech"
)


def generate_image_bytes(
    api_host: str,
    api_key: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int = 30,
    cfg_scale: float = 7.0,
) -> bytes:
    model = "stable-diffusion-xl-1024-v1-0"
    url = f"{api_host}/v1/generation/{model}/text-to-image"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "text_prompts": [
            {"text": prompt, "weight": 1},
            {"text": negative_prompt, "weight": -1},
        ],
        "cfg_scale": cfg_scale,
        "width": width,
        "height": height,
        "samples": 1,
        "steps": steps,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(f"Text-to-image failed: {resp.status_code} {resp.text}")
    data = resp.json()
    b64 = data["artifacts"][0]["base64"]
    return base64.b64decode(b64)


# --- HeyGen integration ---

def _compute_aspect_ratio_string(width: int, height: int) -> str:
    # Simple mapping to common strings HeyGen understands; fallback to WxH string
    # Rounded to typical presets.
    if width == height:
        return "1:1"
    # Prefer 16:9 vs 9:16 based on orientation
    if abs((width / height) - (16 / 9)) < 0.02:
        return "16:9"
    if abs((width / height) - (9 / 16)) < 0.02:
        return "9:16"
    if abs((width / height) - (4 / 3)) < 0.02:
        return "4:3"
    if abs((width / height) - (3 / 4)) < 0.02:
        return "3:4"
    return f"{width}x{height}"


def submit_heygen_talking_photo(
    api_host: str,
    api_key: str,
    image_bytes: bytes,
    script_text: str,
    voice_id: str,
    width: int,
    height: int,
) -> str:
    """Submit a talking-photo job to HeyGen.

    Tries the commonly used `v1/video.create` endpoint with an inline data URL image.
    Returns a video_id which can be used to poll status.
    """
    url = f"{api_host.rstrip('/')}/v1/video.create"
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:image/png;base64,{image_b64}"

    aspect = _compute_aspect_ratio_string(width, height)

    payload: Dict[str, Any] = {
        "video_inputs": [
            {
                "character": {
                    "type": "image",
                    # Prefer data URL to avoid external hosting. Some versions accept this.
                    "image_url": image_data_url,
                },
                "voice": {
                    "voice_id": voice_id,
                    "input_text": script_text,
                },
            }
        ],
        # Some APIs prefer `dimension`, some prefer `aspect_ratio`. We include both.
        "dimension": {"width": width, "height": height},
        "aspect_ratio": aspect,
    }

    print(f"[debug] POST {url}")
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"[debug] status={resp.status_code} body={resp.text[:500]}")
    if resp.status_code not in (200, 201, 202):
        # Provide hint for alternate endpoint naming
        raise RuntimeError(
            "HeyGen submit failed: "
            f"{resp.status_code} {resp.text[:500]}\n"
            "If this persists, verify endpoint /v1/video.create and payload format."
        )
    data = resp.json()
    # Common responses: {"data": {"video_id": "..."}} or {"video_id": "..."}
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
    """Poll HeyGen video status, download when ready."""
    status_url = f"{api_host.rstrip('/')}/v1/video.status"
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
    }
    start = time.time()
    while True:
        params = {"video_id": video_id}
        resp = requests.get(status_url, headers=headers, params=params, timeout=90)
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


# --- Legacy Stability image-to-video kept for optional use ---

def submit_image_to_video(api_host, api_key, image_bytes, seed=0, cfg_scale=1.8, motion_bucket_id=127):
    candidates = [
        (f"{api_host}/v2alpha/generation/image-to-video", "v2alpha_generation"),
        (f"{api_host}/v2beta/image-to-video", "v2beta"),
    ]
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    data = {"seed": str(seed), "cfg_scale": str(cfg_scale), "motion_bucket_id": str(motion_bucket_id)}
    last_error = None
    for url, variant in candidates:
        print(f"[debug] POST {url}")
        files = {"image": ("frame.png", io.BytesIO(image_bytes), "image/png")}
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=90)
        print(f"[debug] status={resp.status_code} body={resp.text[:500]}")
        if resp.status_code == 200:
            job = resp.json()
            generation_id = job.get("id") or job.get("generation_id") or job.get("result", {}).get("id")
            if generation_id:
                return generation_id, variant
            last_error = f"Unexpected response: {job}"
            continue
        if resp.status_code in (404, 405):
            last_error = f"{resp.status_code} {resp.text}"
            continue
        raise RuntimeError(f"Image-to-video submit failed: {resp.status_code} {resp.text}")
    raise RuntimeError(f"Image-to-video submit failed (all tried): {last_error}")


def poll_video_result(
    api_host: str,
    api_key: str,
    generation_id: str,
    out_path: Path,
    submit_variant: str,
    poll_interval_sec: int = 8,
    max_wait_sec: int = 900,
) -> Path:
    candidates = []
    if submit_variant == "v2alpha_generation":
        candidates.append(f"{api_host}/v2alpha/generation/image-to-video/result/{generation_id}")
        candidates.append(f"{api_host}/v2beta/image-to-video/result/{generation_id}")
    else:
        candidates.append(f"{api_host}/v2beta/image-to-video/result/{generation_id}")
        candidates.append(f"{api_host}/v2alpha/generation/image-to-video/result/{generation_id}")
    candidates = list(dict.fromkeys(candidates))  # de-dup while preserving order

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "video/*",
    }
    start = time.time()
    for url in candidates:
        while True:
            resp = requests.get(url, headers=headers, timeout=90)
            if resp.status_code == 202:
                if time.time() - start > max_wait_sec:
                    raise TimeoutError("Timed out waiting for video result.")
                time.sleep(poll_interval_sec)
                continue
            if resp.status_code == 200:
                out_path.write_bytes(resp.content)
                return out_path
            if resp.status_code == 404:
                break  # try next candidate
            raise RuntimeError(f"Video result error: {resp.status_code} {resp.text}")
    raise RuntimeError("Video result not found on any known endpoint variant.")


def main():
    parser = argparse.ArgumentParser()
    # Stability (preview image)
    parser.add_argument("--api-key")
    parser.add_argument("--api-host", default=os.getenv("API_HOST", "https://api.stability.ai"))
    # HeyGen
    parser.add_argument("--provider", choices=["heygen", "stability"], default="heygen")
    parser.add_argument("--heygen-api-key")
    parser.add_argument("--heygen-api-host", default=os.getenv("HEYGEN_API_HOST", "https://api.heygen.com"))
    parser.add_argument("--heygen-voice-id", help="HeyGen voice id to use for speech")

    # Prompting
    parser.add_argument("--character-key", required=True)
    parser.add_argument("--identity-descriptor", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--segment-text", required=True)

    # Dimensions and output
    parser.add_argument("--width", type=int, default=1344)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--snap-dims", action="store_true", default=True, help="Auto-snap to valid SDXL dims")
    parser.add_argument("--out-dir", default="outputs")

    # Image generation controls
    parser.add_argument("--image-steps", type=int, default=30)
    parser.add_argument("--image-cfg", type=float, default=7.0)

    # Stability image-to-video controls (legacy path)
    parser.add_argument("--video-seed", type=int, default=0)
    parser.add_argument("--video-cfg", type=float, default=1.8)
    parser.add_argument("--video-motion", type=int, default=127)

    args = parser.parse_args()

    # Resolve keys
    stability_api_key = resolve_api_key(args.api_key)
    heygen_api_key = resolve_heygen_api_key(args.heygen_api_key) if args.provider == "heygen" else None

    # Dimensions
    width, height = args.width, args.height
    if args.snap_dims and (width, height) not in ALLOWED_SDXL_DIMS:
        snapped_w, snapped_h = snap_sdxl_dims(width, height)
        print(f"[info] Snapping SDXL dims {width}x{height} -> {snapped_w}x{snapped_h}")
        width, height = snapped_w, snapped_h

    # Prompt
    prompt = build_prompt(
        character_key=args.character_key,
        identity_descriptor=args.identity_descriptor,
        company_name=args.company_name,
        segment_text=args.segment_text,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Preview image
    print("[step] Generating preview image...")
    image_bytes = generate_image_bytes(
        api_host=args.api_host,
        api_key=stability_api_key,
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        width=width,
        height=height,
        steps=args.image_steps,
        cfg_scale=args.image_cfg,
    )
    preview_path = out_dir / "preview_frame.png"
    preview_path.write_bytes(image_bytes)
    print(f"[ok] Preview saved: {preview_path}")

    if args.provider == "heygen":
        if not heygen_api_key:
            raise RuntimeError("HeyGen chosen but missing --heygen-api-key or HEYGEN_API_KEY")
        if not args.heygen_voice_id:
            raise RuntimeError("HeyGen requires --heygen-voice-id")

        print("[step] Submitting HeyGen talking-photo job...")
        video_id = submit_heygen_talking_photo(
            api_host=args.heygen_api_host,
            api_key=heygen_api_key,
            image_bytes=image_bytes,
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
    else:
        # Legacy Stability image->video path
        print("[step] Submitting image-to-video job (Stability legacy)...")
        generation_id, submit_variant = submit_image_to_video(
            api_host=args.api_host,
            api_key=stability_api_key,
            image_bytes=image_bytes,
            seed=args.video_seed,
            cfg_scale=args.video_cfg,
            motion_bucket_id=args.video_motion,
        )
        print(f"[ok] Job submitted. generation_id={generation_id}")

        print("[step] Polling for video result...")
        video_path = out_dir / f"video_{generation_id}.mp4"
        final_path = poll_video_result(
            api_host=args.api_host,
            api_key=stability_api_key,
            generation_id=generation_id,
            out_path=video_path,
            submit_variant=submit_variant,
        )
        print(f"[done] Video saved: {final_path}")


if __name__ == "__main__":
    main()
