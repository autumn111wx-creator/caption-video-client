# 视频字幕客户端

Windows 桌面字幕工具。选择一段视频、导入或粘贴文字，即可生成配音和带字幕视频；没有选择视频时，默认生成纯黑背景。

## 下载试用

当前版本：**v3.0.0-beta.1**（2026-09-15）。

前往 [Releases](https://github.com/autumn111wx-creator/caption-video-client/releases/tag/v3.0.0-beta.1) 下载 `caption-video-client-v3.0.0-beta.1-windows-x64.zip`，完整解压后双击 `黑底字幕视频工具.exe`。请保留旁边的 `_internal`、`bin` 和配置文件夹。

运行环境：Windows 10/11 x64，Microsoft Edge WebView2 Runtime；自然语音合成需要联网。便携包内置 Python 和 FFmpeg。

## 功能

- 独立客户端窗口、底部状态栏、Windows 托盘菜单与退出入口。
- 可选背景视频：MP4、MOV、MKV、WebM、AVI、WMV、M4V、FLV。
- 文字导入 TXT / SRT，支持直接粘贴。
- 配音速度 0.5–2.0 倍，界面步长 0.1。
- 视频输出 MP4 / MOV / MKV / WebM / AVI。
- 音频输出 WAV / MP3 / M4A / FLAC / OGG，并输出 SRT 字幕。
- 音色 JSON 文件放入 `音色配置/`，重启后识别；发音词典仅改变朗读。

## 当前行为和限制

- 所选视频作为背景画面；短视频循环、长视频裁切到配音时长。输出固定为 1920×1080，画面等比放大并居中裁切。
- 使用新配音替换原视频声音。目前没有保留原声、自动听写视频语音的功能。
- SRT 导入提取正文，按新配音重新生成时间轴，不保留原时间码。
- 仅 MP4/WebM 提供内嵌预览；其他格式可从成品目录打开。
- Edge TTS 会将待朗读文字发送至在线语音服务；视频处理在本机进行。
- 本次发布归档桌面试用版及其原始核心源码，未额外修改生成逻辑。旧命令行入口仍有开发机默认路径；开发时请显式传入 `--input`，并把 FFmpeg/FFprobe 放进 `bin/`，或设置 `FFMPEG_EXE`。

详见 [客户端配置说明](客户端配置说明.txt) 和 [版本记录](CHANGELOG.md)。

## 源码运行

在 Windows PowerShell 中：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
# 把 ffmpeg.exe 和 ffprobe.exe 放入 bin 文件夹
.\.venv\Scripts\python.exe portable_app.py
```

## 构建便携包

使用同一环境，准备 `bin/ffmpeg.exe`、`bin/ffprobe.exe` 后执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

脚本先构建客户端，再复制运行所需组件，生成一个带时间戳的独立发布目录和 ZIP。构建结果位于 `dist/`。发布前请核对所用 FFmpeg 构建的许可和再分发要求，附上对应许可材料。

## 目录

| 文件 | 用途 |
| --- | --- |
| `portable_app.py` | 客户端窗口、托盘、本地接口与任务管理 |
| `make_caption_video.py` | 配音、字幕时间轴、视频生成 |
| `ui/index.html` | 中文客户端界面 |
| `音色配置/` | 音色配置及示例 |
| `CaptionVideoClient.spec` | PyInstaller 构建配置 |
| `scripts/build.ps1` | 打包脚本 |
| `releases/v3.0.0-beta.1.json` | 已发布文件的大小、SHA256 和版本说明 |

## 版本管理约定

`main` 保存当前源码。每次交付使用独立标签和 Release；修改记录写入 `CHANGELOG.md`。试用问题请在 [Issues](https://github.com/autumn111wx-creator/caption-video-client/issues) 提交复现步骤、输入格式和报错。请先去掉截图、日志中的私人文稿或敏感信息。

源码仓库不包含测试成品、日志、虚拟环境和视频素材。当前桌面 ZIP 原样作为 Release 附件归档，校验值见发布清单。

## 开源依赖

基于 FFmpeg、edge-tts、pywebview、pystray、FastAPI、Uvicorn，早期工具与 Story2Video 项目有关；参考 auto-subtitle 的视频字幕叠加流程。详见 [开源项目说明](开源项目说明.txt) 和 `licenses/`。各第三方项目遵循各自许可；本仓库未额外授予自有代码的开源许可证。
