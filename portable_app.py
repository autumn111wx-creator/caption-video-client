"""Native Windows client for producing narrated black-background subtitle video."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import threading
import time
import traceback
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

import make_caption_video as pipeline


APP_NAME = "黑底字幕视频工具"
APP_VERSION = "3.0 试用版"
ROOT = pipeline.ROOT
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
UI_FILE = RESOURCE_ROOT / "ui" / "index.html"
INBOX = ROOT / "work" / "inbox"
OUTPUT = ROOT / "成品"
DICTIONARY = ROOT / "发音词典.tsv"
VOICE_DIR = ROOT / "音色配置"
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="caption-render")
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()
APP_LOCK = threading.Lock()
SERVER = None
WINDOW = None
TRAY = None
EXITING = False

VIDEO_FORMATS = {
    "mp4": {"label": "MP4 · 通用推荐", "mime": "video/mp4"},
    "mov": {"label": "MOV · 剪辑软件", "mime": "video/quicktime"},
    "mkv": {"label": "MKV · 高清封装", "mime": "video/x-matroska"},
    "webm": {"label": "WebM · 网页视频", "mime": "video/webm"},
    "avi": {"label": "AVI · 传统兼容", "mime": "video/x-msvideo"},
}
AUDIO_FORMATS = {
    "wav": {"label": "WAV · 无损推荐", "mime": "audio/wav"},
    "mp3": {"label": "MP3 · 最通用", "mime": "audio/mpeg"},
    "m4a": {"label": "M4A · 体积较小", "mime": "audio/mp4"},
    "flac": {"label": "FLAC · 无损压缩", "mime": "audio/flac"},
    "ogg": {"label": "OGG · 开源格式", "mime": "audio/ogg"},
}
BUILTIN_VOICES = [
    {"name": "晓晓 · 女声", "voice": "zh-CN-XiaoxiaoNeural", "source": "内置"},
    {"name": "云希 · 男声", "voice": "zh-CN-YunxiNeural", "source": "内置"},
    {"name": "晓伊 · 女声", "voice": "zh-CN-XiaoyiNeural", "source": "内置"},
    {"name": "云健 · 男声", "voice": "zh-CN-YunjianNeural", "source": "内置"},
    {"name": "云扬 · 男声", "voice": "zh-CN-YunyangNeural", "source": "内置"},
]
VOICE_ID = re.compile(r"^[A-Za-z]{2,3}-[A-Za-z]{2,4}-[A-Za-z0-9]+Neural$")


app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)


class CreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=30000)
    filename: str = "文稿.txt"
    voice: str = "zh-CN-XiaoxiaoNeural"
    speed: float = Field(default=0.9, ge=0.5, le=2.0)
    video_format: str = "mp4"
    audio_format: str = "wav"
    source_video: str | None = None


def safe_stem(name: str) -> str:
    stem = Path(name.replace("\\", "/").split("/")[-1]).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    return (stem or "文稿")[:55]


def srt_to_text(text: str) -> str:
    """Extract cue text from SRT while accepting common imperfect files."""
    cues: list[str] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines()]
        timing = next((index for index, line in enumerate(lines) if "-->" in line), -1)
        if timing >= 0:
            cue = " ".join(line for line in lines[timing + 1 :] if line)
            if cue:
                cues.append(cue)
    if not cues:
        raise RuntimeError("没有从 SRT 中识别到字幕内容，请检查时间轴格式。")
    return "\n".join(cues)


def ensure_voice_folder() -> None:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    guide = VOICE_DIR / "添加音色说明.txt"
    if not guide.exists():
        guide.write_text(
            "把 .json 音色配置放进本目录，重启软件后自动出现在音色列表。\n\n"
            "格式示例：\n"
            '{\n  "name": "云扬 · 男声",\n  "voice": "zh-CN-YunyangNeural"\n}\n\n'
            "说明：这里保存的是 Edge TTS 音色配置，不是录音文件；合成语音需要联网。\n",
            encoding="utf-8-sig",
        )


def load_voices() -> list[dict[str, str]]:
    ensure_voice_folder()
    configured: list[dict[str, str]] = []
    for path in sorted(VOICE_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            entries = raw if isinstance(raw, list) else [raw]
            for entry in entries:
                name = str(entry.get("name", "")).strip()
                voice = str(entry.get("voice", "")).strip()
                if name and VOICE_ID.fullmatch(voice):
                    configured.append({"name": name, "voice": voice, "source": path.name})
        except Exception:
            continue
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in configured + BUILTIN_VOICES:
        if item["voice"] not in seen:
            seen.add(item["voice"])
            merged.append(item)
    return merged


def set_job(job_id: str, **fields) -> None:
    with LOCK:
        JOBS[job_id].update(fields)


def convert_outputs(folder: Path, stem: str, video_format: str, audio_format: str, progress) -> dict[str, Path]:
    video_source = folder / f"{stem}.mp4"
    audio_source = folder / f"{stem}.wav"
    srt_path = folder / f"{stem}.srt"
    ffmpeg, _ = pipeline.find_ffmpeg()

    video_target = folder / f"{stem}.{video_format}"
    if video_format != "mp4":
        progress(f"正在转换 {video_format.upper()} 视频…")
        commands = {
            "mov": ["-c", "copy", "-movflags", "+faststart"],
            "mkv": ["-c", "copy"],
            "webm": ["-c:v", "libvpx-vp9", "-crf", "31", "-b:v", "0", "-c:a", "libopus", "-b:a", "128k"],
            "avi": ["-c:v", "mpeg4", "-q:v", "4", "-c:a", "libmp3lame", "-b:a", "160k"],
        }
        pipeline.execute(
            [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(video_source), *commands[video_format], str(video_target)],
            folder / f"convert_{video_format}.log",
        )

    audio_target = folder / f"{stem}.{audio_format}"
    if audio_format != "wav":
        progress(f"正在转换 {audio_format.upper()} 音频…")
        commands = {
            "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
            "m4a": ["-c:a", "aac", "-b:a", "192k"],
            "flac": ["-c:a", "flac"],
            "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
        }
        pipeline.execute(
            [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(audio_source), *commands[audio_format], str(audio_target)],
            folder / f"convert_{audio_format}.log",
        )

    if video_format != "mp4":
        video_source.unlink(missing_ok=True)
    if audio_format != "wav":
        audio_source.unlink(missing_ok=True)
    for log in folder.glob("convert_*.log"):
        log.unlink(missing_ok=True)
    return {"video": video_target, "audio": audio_target, "srt": srt_path}


def worker(job_id: str, request: CreateRequest) -> None:
    job_inbox: Path | None = None
    try:
        INBOX.mkdir(parents=True, exist_ok=True)
        stem = safe_stem(request.filename)
        job_inbox = INBOX / job_id
        job_inbox.mkdir()
        text = srt_to_text(request.text) if Path(request.filename).suffix.lower() == ".srt" else request.text
        source = job_inbox / f"{stem}.txt"
        source.write_text(text, encoding="utf-8")

        def report(message: str) -> None:
            set_job(job_id, message=message)

        rate = round((request.speed - 1.0) * 100)
        background_video = Path(request.source_video) if request.source_video else None
        if background_video is not None:
            if not background_video.is_file():
                raise RuntimeError("找不到已选择的背景视频，请重新选择。")
            if background_video.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".wmv", ".m4v", ".flv"}:
                raise RuntimeError("背景视频格式不支持，请选择常用视频文件。")
        folder = pipeline.generate(
            source,
            OUTPUT,
            request.voice,
            rate,
            DICTIONARY,
            44,
            report,
            background_video=background_video,
        )
        files = convert_outputs(folder, stem, request.video_format, request.audio_format, report)
        record_path = folder / "制作记录.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record.update(
            {
                "app_version": APP_VERSION,
                "speed": request.speed,
                "input_format": Path(request.filename).suffix.lower().lstrip(".") or "txt",
                "video_format": request.video_format,
                "audio_format": request.audio_format,
                "background_video": str(background_video) if background_video else None,
            }
        )
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        set_job(
            job_id,
            state="done",
            folder=str(folder),
            files={key: str(path) for key, path in files.items()},
            formats={"video": request.video_format, "audio": request.audio_format, "srt": "srt"},
            message="制作完成，三个成品已保存。",
        )
    except Exception as exc:
        set_job(job_id, state="error", message=str(exc))
        (ROOT / "work").mkdir(parents=True, exist_ok=True)
        (ROOT / "work" / f"error_{job_id}.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        if job_inbox is not None and job_inbox.exists():
            shutil.rmtree(job_inbox, ignore_errors=True)


@app.get("/")
def index():
    return HTMLResponse(UI_FILE.read_text(encoding="utf-8"))


@app.get("/api/config")
def config():
    voices = load_voices()
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "voices": voices,
        "voice_count": len(voices),
        "video_formats": VIDEO_FORMATS,
        "audio_formats": AUDIO_FORMATS,
        "voice_folder": str(VOICE_DIR),
        "output_folder": str(OUTPUT),
        "video_inputs": ["mp4", "mov", "mkv", "webm", "avi", "wmv", "m4v", "flv"],
    }


@app.post("/api/create")
def create(request: CreateRequest):
    if not request.text.strip():
        raise HTTPException(400, "请先输入或导入文字。")
    if request.video_format not in VIDEO_FORMATS:
        raise HTTPException(400, "不支持所选视频格式。")
    if request.audio_format not in AUDIO_FORMATS:
        raise HTTPException(400, "不支持所选音频格式。")
    if request.voice not in {item["voice"] for item in load_voices()}:
        raise HTTPException(400, "音色配置无效，请重启软件后重试。")
    job_id = uuid.uuid4().hex[:12]
    with LOCK:
        JOBS[job_id] = {"state": "running", "message": "正在准备文稿…"}
    EXECUTOR.submit(worker, job_id, request)
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def job(job_id: str):
    with LOCK:
        info = JOBS.get(job_id)
        if info is None:
            raise HTTPException(404, "任务不存在或软件已重启。")
        data = {key: value for key, value in info.items() if key != "files"}
    if data["state"] == "done":
        data["urls"] = {key: f"/api/file/{job_id}/{key}" for key in ("video", "audio", "srt")}
    return data


@app.get("/api/file/{job_id}/{kind}")
def file(job_id: str, kind: str):
    if kind not in {"video", "audio", "srt"}:
        raise HTTPException(404)
    with LOCK:
        info = JOBS.get(job_id)
        path_text = info.get("files", {}).get(kind) if info and info.get("state") == "done" else None
        formats = info.get("formats", {}) if info else {}
    path = Path(path_text) if path_text else None
    if path is None or not path.is_file():
        raise HTTPException(404)
    extension = formats.get(kind, "srt")
    mime = VIDEO_FORMATS.get(extension, AUDIO_FORMATS.get(extension, {"mime": "text/plain; charset=utf-8"}))["mime"]
    return FileResponse(path, media_type=mime, filename=path.name)


@app.get("/api/health")
def health():
    return {"app": APP_NAME, "version": APP_VERSION}


@app.post("/api/app/exit")
def exit_route():
    threading.Timer(0.15, request_exit).start()
    return {"ok": True}


def open_path(path: Path) -> bool:
    if path == OUTPUT:
        path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))
        return True
    return False


class NativeApi:
    def pick_video(self):
        import webview

        if WINDOW is None:
            return None
        result = WINDOW.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("视频文件 (*.mp4;*.mov;*.mkv;*.webm;*.avi;*.wmv;*.m4v;*.flv)", "所有文件 (*.*)"),
        )
        if not result:
            return None
        return str(result[0] if isinstance(result, (tuple, list)) else result)

    def open_output(self):
        return open_path(OUTPUT)

    def open_voices(self):
        ensure_voice_folder()
        return open_path(VOICE_DIR)

    def exit_app(self):
        threading.Thread(target=request_exit, daemon=True).start()
        return True


def request_exit(*_args) -> None:
    global EXITING
    with APP_LOCK:
        if EXITING:
            return
        EXITING = True
    if TRAY is not None:
        try:
            TRAY.stop()
        except Exception:
            pass
    if SERVER is not None:
        SERVER.should_exit = True
    if WINDOW is not None:
        try:
            WINDOW.destroy()
        except Exception:
            pass


def tray_icon_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (20, 28, 44, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(40, 99, 235, 255))
    draw.polygon([(20, 17), (49, 32), (20, 47)], fill=(255, 255, 255, 255))
    draw.rectangle((13, 51, 51, 55), fill=(77, 225, 184, 255))
    return image


def start_tray() -> None:
    global TRAY
    import pystray

    def show_window(_icon=None, _item=None):
        if WINDOW is not None:
            WINDOW.show()
            WINDOW.restore()

    def open_output(_icon=None, _item=None):
        open_path(OUTPUT)

    TRAY = pystray.Icon(
        "CaptionVideoClient",
        tray_icon_image(),
        f"{APP_NAME} · 运行中",
        pystray.Menu(
            pystray.MenuItem("打开主窗口", show_window, default=True),
            pystray.MenuItem("打开成品文件夹", open_output),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出软件", request_exit),
        ),
    )
    TRAY.run_detached()


def find_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_for_server(port: int) -> None:
    import urllib.request

    url = f"http://127.0.0.1:{port}/api/health"
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=0.2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("客户端服务启动超时。")


def main() -> None:
    global SERVER, WINDOW
    import uvicorn
    import webview

    ensure_voice_folder()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    port = find_port()
    SERVER = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server_thread = threading.Thread(target=SERVER.run, name="local-api", daemon=True)
    server_thread.start()
    wait_for_server(port)

    WINDOW = webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{port}/",
        js_api=NativeApi(),
        width=1180,
        height=820,
        min_size=(960, 680),
        background_color="#0b1220",
        text_select=True,
    )
    WINDOW.events.closed += request_exit
    start_tray()
    try:
        webview.start(gui="edgechromium", debug=False, private_mode=True)
    finally:
        request_exit()
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
