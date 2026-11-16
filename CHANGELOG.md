---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: b39d940f30a0c1cf547a23c927f28498_409e77bee18b11f1a768525400cd780f
    ReservedCode1: IxzQRiTMxO4FaP6z6eCD3PgqUBBJLHtdLnTgAVSbvDuU8CpK6oW1r09M5WYHWkPRJWGX6atvdiSndFU5yjHliW+vJLg7kX7nL90hNopjEszZOnuqZkFyeeRUO7ov9bfXRvNk6c9wTekxJDk0s8SaXFUDFb5CcXN3L7fDVmZzKTwXNyASbLipHPy+eko=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: b39d940f30a0c1cf547a23c927f28498_409e77bee18b11f1a768525400cd780f
    ReservedCode2: IxzQRiTMxO4FaP6z6eCD3PgqUBBJLHtdLnTgAVSbvDuU8CpK6oW1r09M5WYHWkPRJWGX6atvdiSndFU5yjHliW+vJLg7kX7nL90hNopjEszZOnuqZkFyeeRUO7ov9bfXRvNk6c9wTekxJDk0s8SaXFUDFb5CcXN3L7fDVmZzKTwXNyASbLipHPy+eko=
---

﻿# 更新日志

本项目遵循语义化版本（`主版本.次版本.修订号`）。每个版本对应的可执行文件见 [Releases](https://github.com/yangshuang9889/MdCmdTool/releases)。

> 提示：程序内「帮助 → 检查更新」读取的正是这里的 Release 版本号与说明，发版时请同步创建 Release 并填写更新内容。

## v1.10.1（2026-11-16）
**修复：预览区视频就是放不出来（`isOutside=true` 导致 B 站只回一帧静止画面）**
- 根因：B 站播放地址模板里带了 `isOutside=true`。B 站收到该参数会按「站外引用」降级返回，内嵌窗口里只剩一帧静止画面——实测该区域整块接近全黑（亮度采样 nonblack≈0.0011），连续两次截图帧差≈0.0004，肉眼看就是黑屏；同一个 BV 号去掉该参数后立即出动态画面。
- 修复：`BILI_PLAYER_URL` 去掉 `isOutside=true`，改为 `autoplay=1&high_quality=1&danmaku=1`；`bili_embed_src()` 拼地址也不再追加该参数。
- 新增 `bili_clean_url()`：用户从网上抄来的旧 iframe / 播放器地址里带的 `isOutside`，在「插入标记」「预览播放页」「浏览器打开」三处统一摘掉，老文档不用重写。
- 剥离动作写入日志（`logs\sg-md-editor-*.log`），出问题可直接复核最终播放地址。
- 只删这一个参数，`bvid` / `cid` / `page` / `autoplay` / `high_quality` / `danmaku` 等其余参数原样保留。
- 实测（v1.10.1 生成的播放页，Edge 内嵌同款窗口）：`BV1Uesp6yEsM` 亮度采样 nonblack=0.9955、连续两帧帧差 0.6319 → 动态画面正常起播；对照修复前同一视频 nonblack≈0.0011 / 帧差≈0.0004（静止黑屏）。
- 回归：新增 `scripts/verify_video_v111.py`（28 / 28）；`verify_video_v180.py` 62 / 62、`verify_video_v181.py` 25 / 25、`verify_video_v110.py` 57 / 57、`verify_context_v190.py` 60 / 60、`verify_images_v170.py` 34 / 34、`verify_unsaved_v150.py` 25 / 25、`verify_update_v160.py` 28 / 28 全绿；`check_manual_lines.py` 失败 0。
- 手册同步：`开发手册.md` 行号引用按新源码重算（`scripts/fix_manual_lines_v111.py`），并补记 `bili_clean_url` 的调用链与「不得再加 isOutside」的红线。
- 版本号同步：`APP_VERSION` → `1.10.1`、`version_info.txt` → `1.10.1.0`。

## v1.10.0（2026-11-16）
**修复：预览区面板被压成 61 像素、播放窗口反复复用**
- 视频面板改为挂在主窗口底部（`before=self.paned`），面板高度按 `VIDEO_PANEL_MIN_W` / `VIDEO_PANEL_MAX_H` 限制，不再被主分栏挤成 61 像素。
- 每次播放使用独立 Edge 配置目录（`video_cache\profiles\`，保留最近 `VIDEO_PROFILE_KEEP` 个），避免复用旧进程导致「窗口起了但没画面」。
- 播放页与本地视频改由本机回环 HTTP 服务提供（`VideoHttpServer`，127.0.0.1 随机端口）：`file://` 下 Chromium 会卡住跨源媒体与 iframe Referer，本地视频还支持 Range 以便拖动进度。
- 本地 / 直链视频起播加固：先静音起播、成功后取消静音，失败重试 30 次并给出「视频加载失败」提示。
- 全程日志加固：Edge 启动参数、pid、hwnd 轮询、样式位前后值、嵌入轮询次数、进程返回码全部落 `logs\`。

## v1.9.0（2026-11-16）
**新增：输入框全中文右键菜单**
- 三个输入区——左栏「① 命令速查录入」、中栏「② Markdown 编辑器」、右栏「③ 实时预览」——右键即可弹出中文菜单，不再落到 tkinter 的英文默认菜单或干脆没反应。
- 可编辑区菜单项：撤销 / 重做 / 剪切 / 复制 / 粘贴 / 删除 / 全选（带 `Ctrl+Z` / `Ctrl+Y` / `Ctrl+X` / `Ctrl+C` / `Ctrl+V` / `Del` / `Ctrl+A` 快捷键提示）。
- 置灰规则按场景实时计算（每次弹出前重算，不用先点一下才准）：
  - 撤销 / 重做 → 看该控件的撤销栈是否可用（`edit canundo` / `edit canredo`）；
  - 剪切 / 复制 / 删除 → 只有存在选区才亮；
  - 粘贴 → 剪贴板里确实有文本才亮；
  - 全选 → 控件里有内容才亮。
- 只读控件（实时预览、更新弹窗里的说明文本）只保留「复制 / 全选」，剪切 / 粘贴 / 删除 / 撤销直接不出现在菜单里，避免点了没反应。
- 菜单跟随主题：浅色 / 深色切换时背景、前景、高亮色与主菜单栏保持同一套配色。
- 通过右键菜单改动编辑器内容后，脏标记、预览、字数统计立即刷新，与手动输入一致。
- 其他输入位置同步覆盖：插入视频的多行输入框（`_ask_video_text`）、更新弹窗的说明文本（`UpdateDialog`）；`tk.Entry` / `ttk.Entry` 类控件同样通用。
- 回归：新增 `scripts/verify_context_v190.py` 60 / 60 PASS；`verify_video_v181.py` 23 / 23、`verify_images_v170.py` 34 / 34、`verify_unsaved_v150.py` 25 / 25、`verify_update_v160.py` 28 / 28、`verify_video_v180.py` 62 / 62 全绿；开发手册行号校验引用 302 条（通过 266 / 失败 0 / 非符号 36 条已逐条登记）、越界 0。
- 回归脚本维护：`scripts/verify_video_v180.py` 中「`APP_VERSION` 必须等于 `1.8.0`」的版本锁定断言改为「不低于 `1.8.0`」，避免后续版本推进后误报。
- 版本号同步：`APP_VERSION` → `1.9.0`、`version_info.txt` → `1.9.0.0`。
- 产物：`dist\SgMdEditor-v1.9.0.exe`（30,949,625 字节，FileVersion / ProductVersion 均为 `1.9.0.0`，冒烟启动标题显示 `爽哥MD编辑工具 v1.9.0`）。

## v1.8.1（2026-11-16）

**修复：插入视频不好使**

- 现象：点「插入视频」（`Ctrl+Shift+V`）后插进文档的是剪贴板里的一大段普通文字，没有任何提示，连点多次结果相同。
- 根因：`build_video_markup` 只要整段文本中出现 `"<iframe"` / `"<video"` 或以下载链接开头，就把整段原样当视频标记返回；剪贴板里沾到手册里的 iframe 示例或某个链接就会被整段塞进文档。
- 修复：
  - 新增 `video_markup_pure()` / `url_like()` 双重纯净度判定：只接受「整段就是一个视频标记 / 地址」，夹带正文一律判失败；
  - `insert_video()` 重写：剪贴板不干净时不再硬塞，改为弹出新的**多行输入框**（`_ask_video_text`，`Ctrl+Enter` 确定 / `Esc` 取消 / 「选择本地视频…」），并提示「剪贴板内容不是可识别的视频，已忽略」；
  - 识别失败给出明确 `messagebox`（列出支持的四类输入）；插入后滚动到插入点，状态栏标注来源（剪贴板 / 手动输入 / 本地文件）。
- 回归：新增 `scripts/verify_video_v181.py` 23 / 23 PASS；`verify_video_v180.py` 62 / 62、`verify_images_v170.py` 34 / 34、`verify_unsaved_v150.py` 25 / 25 全绿；开发手册行号校验失败 0 / 越界 0。
- 版本号同步：`APP_VERSION` → `1.8.1`、`version_info.txt` → `1.8.1.0`。

## v1.8.0（2026-11-16）

**新增：预览区播放视频**

- 预览区能识别 Markdown 里的视频并**在预览栏内直接播放**，支持四类输入：B 站 `iframe` 样板、B 站视频页地址 / `BV` 号、任意网页视频地址、本地视频文件路径；
- 识别到的视频在预览区显示为一行 `▶ 播放视频：<说明>`，单击即在预览栏底部的播放面板里播放，不用跳出编辑器；
- 播放面板 16:9 自适应，带「浏览器打开」（默认浏览器打开原地址）与「关闭」两个按钮；Edge 缺失时自动降级为浏览器打开；
- B 站地址若已带 `cid` 参数原样透传，只给 `BV` 号时按默认播放地址拼接；
- 播放用临时页面写入程序目录的 `video_cache\`，**不上传任何内容、不联网上报**；退出程序时清理播放进程，不留残留。

**新增：工具栏「插入视频」按钮**

- 工具栏新增 **插入视频** 按钮（`Ctrl+Shift+V`，在「插入图片」之后）：输入框接受站内地址 / `BV` 号 / 网页地址 / 本地路径，按类型插入 `iframe` 或 `<video>` 片段；
- 插入的 B 站样板默认 16:9、`allowfullscreen`、`loading="lazy"`，宽度自适应容器。

**工程**

- 新增验证脚本 `scripts\verify_video_v180.py`（62 项），图片 / 未保存 / 检查更新三组回归全绿，开发手册行号校验 0 失败 0 越界；
- 版本号同步：`APP_VERSION` → `1.8.0`、`version_info.txt` → `1.8.0.0`。

## v1.7.0（2026-11-15）

**新增：预览区显示图片**

- 预览区不再只显示 `![说明](路径)` 源码，而是**渲染成真实图片**：本地 `PNG` / `JPG` / `JPEG` / `GIF` / `BMP` / `WEBP` 均可直接看图；
- 路径解析：相对路径**以当前文档所在目录为基准**（未保存的新文档以程序工作目录为基准），同时支持绝对路径与 `file:///D:/a.png` 写法；含空格、中文路径均能正确识别；
- 自适应缩放：按预览区当前宽度等比缩放，图片最大高度 480px、最小宽度兜底 240px，**不会撑破预览区**；
- 单击预览里的图片即可用系统默认看图程序**打开原图**，鼠标悬停变手型，状态栏提示已打开的图片名；
- 改窗口大小或拖动分隔条后自动重排图片（宽度变化超过 60px 触发，420ms 防抖）；
- 优雅降级：网络图片、内嵌 Base64 图片、文件不存在三种情况在预览里显示为一行红色提示文字（写明原因），**不影响其余内容渲染、不弹错误框**；
- 图片缓存：按「路径 + 修改时间 + 最大宽度」缓存已解码图片（上限 32 条），重复预览不反复解码，大文档滚动更顺滑。

**新增：工具栏「插入图片」按钮**

- 工具栏新增 **插入图片** 按钮（在「图片链接」之后），打开文件选择框挑选本地图片，选中后自动写入 `![文件名](相对路径)`；
- 插入时自动计算**相对当前文档目录**的路径，跨盘符无法相对时退回绝对路径，路径含空格自动用 `<>` 包裹，说明文字默认取文件名（不含扩展名）；
- 若编辑区已有选中文本，则把选中文本作为图片说明（`![选中文本](路径)`）；
- 快捷键 **`Ctrl+Shift+I`** 同样触发插入图片；原「图片链接」按钮保持不变（仍是插入待填地址的 `![]()` 模板）。

**依赖说明**

- 无 Pillow 时使用 tkinter 自带 `PhotoImage`，可预览 `PNG` / `GIF` / `PPM`，超过预览宽度时按整数倍降采样；
- 装 Pillow 后（打包环境已装）支持 `JPG` / `JPEG` / `BMP` / `WEBP` 与 LANCZOS 高质量缩放，动图只渲染第一帧避免抖动。

**工程**

- 新增 `scripts/verify_images_v170.py`：标记解析、路径解析与拒绝、插入地址计算、Tk 实渲染（PNG/JPG/GIF/缺失/网络图降级/宽度缩放/缓存复用）、源码静态约束共 34 项校验，全部 PASS；
- 新增 `scripts/fix_manual_lines_v2.py`：按「符号定义行 + 新旧源码 diff 行映射」双路重算开发手册行号引用，实测改写 622 处、校验 0 失败 0 越界；
- 版本号同步至 `APP_VERSION` = `1.7.0` 与 `version_info.txt` = `1.7.0.0`；
- 打包产出 `爽哥MD编辑工具.exe` 31,921,156 字节（FileVersion / ProductVersion = `1.7.0.0`），exe 端实测 5 项：相对路径图、绝对路径图正常显示，文件不存在 / 网络图按提示文字降级，普通链接不受影响；
- 体积提示：因内置 Pillow，exe 由 v1.6.0 的 12,384,743 字节增至 31,921,156 字节；Pillow 为可选依赖，剔除后可回到约 13 MB，但 `JPG` / `BMP` / `WEBP` 将无法预览；
- 已发布 Release：[v1.7.0](https://github.com/yangshuang9889/MdCmdTool/releases/tag/v1.7.0)，资产 `SgMdEditor-v1.7.0.exe` 30,921,156 字节，经 GitHub API 核对与本地 exe 字节数一致。

## v1.6.0（2026-11-15）

**新增：基于开源仓库的在线检查更新**

- 新增 `帮助 → 检查更新...` 菜单项（`Ctrl` 无需记忆快捷键，菜单直达）；
- 关于窗口新增「检查更新」按钮，设置窗口新增「立即检查更新」「打开发布页」按钮与「启动时自动检查更新」开关；
- 检查逻辑：请求 `https://api.github.com/repos/yangshuang9889/MdCmdTool/releases/latest`，解析 `tag_name` / `name` / `body` / `published_at` / `html_url` / `assets`，与本地 `APP_VERSION` 做整数分段比较（支持 `v1.6`、`1.6.0.0` 等写法）；
- 结果三态：**发现新版本**（列出版本号、发布时间、更新说明，并提供「打开发布页 / 下载最新版」）、**已是最新**、**当前版本高于线上**（开发版提示）；
- 网络请求在后台线程执行，超时 8 秒，进度写状态栏；失败只提示原因，不阻塞编辑、不抛出异常弹栈；
- 自动检查默认**关闭**（`settings.json` 的 `auto_check_update`），开启后启动 2.6 秒后静默检查，仅写日志与状态栏，**不弹窗**；
- 安全边界：仅一次匿名只读 HTTPS GET，不下载、不解压、不执行、不静默安装任何内容；发现新版本后由用户自行到发布页下载。

**工程**

- 新增 `scripts/verify_update_v160.py`：版本解析/比较用例、Release 返回体解析、真实接口连通性、配置清洗、源码静态约束共 28 项校验，全部 PASS；
- `build.bat` 重写为带存在性检查、依赖版本打印与完整清理的打包脚本；
- 版本号同步至 `APP_VERSION` 与 `version_info.txt`（1.6.0.0）；
- 仓库开源化：新增 `README.md`、`LICENSE`(MIT)、`CHANGELOG.md`、`SECURITY.md`、`CONTRIBUTING.md`、`.gitignore`、GitHub Actions 打包工作流。

## v1.5.0（2026-11-15）

**新增：未保存修改提示**

- 当前文档有未保存改动时，新建 / 打开 / 退出都先弹「保存 / 不保存 / 取消」，不再静默丢弃内容；
- 脏标记链路：内容快照比对 → 标题追加 `" *"` → 保存或载入后重设基准；
- 新增「保存」（`Ctrl+S`）与「另存为...」（`Ctrl+Shift+S`），原「导出 .md 文件」让位改名；菜单「退出」同样走未保存确认；
- 打开正在编辑的同一文件时只激活窗口，不重载、不弹框；
- 双击转交时序调整为先激活窗口再加载文件，确认框始终位于最前；
- 验证：源码版 25/25 PASS、exe 端到端 8/8 PASS、手册行号校验失败 0。

## v1.4.0（2026-11-15）

**新增：单实例守卫与双击转交**

- 程序已运行时，双击关联 `.md` 不再新起进程，文件直接加载进当前窗口；
- 关联命令改为 `"<exe>" "%1"`，Shell 把文件绝对路径作为第一个参数传入；
- 命名互斥体 `Local\SgMdEditor_SingleInstance_v1` + `127.0.0.1` 回环端口 IPC，首实例把端口写入 `%LOCALAPPDATA%\爽哥MD编辑工具\instance.json`，后续实例转发路径后退出；
- IPC 线程只入队，主线程轮询取出后加载并激活窗口；
- 互斥体或 IPC 任一步失败均降级为「独立进程打开」，不丢功能。

## v1.3.0（2026-11-15）

**更名与外观**

- 应用显示名改为「爽哥MD编辑工具」（源码文件名保留不变）；
- 新增设置窗口（`文件 → 设置...`、`Ctrl+,`），单例复用；
- 黑 / 白两套主题，切换后整窗（菜单、编辑器、预览、状态栏、对话框）即时生效，选择持久化；
- 新增 `.md` 文件关联：仅写 `HKCU\Software\Classes`，可一键取消并还原原打开方式；**启动流程绝不触碰注册表**；
- 新增 `app.ico` / `md_file.ico`（七种尺寸）与 PNG 预览图，`make_icons.py` 可重新生成；
- 修复 `--onefile` 临时解包路径导致关联图标失效：图标先复制到 `%LOCALAPPDATA%\爽哥MD编辑工具\icons\` 再写注册表。

## v1.2.0（2026-11-15）

- 三栏面板显隐：隐藏按钮、视图菜单、`Ctrl+1/2/3` 三入口，至少保留一栏；
- 布局持久化（`settings.json`：`panels` / `geometry` / `sash` / `sash_width`），原子写入 + 严格清洗；
- 新增面板与布局验证脚本。

## v1.1.0

- 20 个语法按钮全部支持「选中即套用」，新增 `H1`~`H6` 与记忆选区机制；
- 完善表格转义、脚注自增、行前缀开关等行为。

## v1.0.0

- 首版：命令速查转表（表格 / 代码清单 / 列表）、Markdown 编辑、实时预览、导出 `.md`、一键复制、日志与异常兜底。
*（内容由AI生成，仅供参考）*
