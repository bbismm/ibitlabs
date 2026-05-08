# EP 1 — The Reveal · Wink 剪辑镜头表

**总时长**: ~43s · **规格**: 1080×1920 · **配音**: 英文主轨 + 中文字幕

## 资源位置
- 字幕卡 PNG: `~/ibitlabs/content/ghost-series/assets/cards/ep01/*.png`
- 字幕 SRT: `~/ibitlabs/content/ghost-series/scripts/ep01_subtitles.srt`
- 英文配音草稿 (macOS say): `~/ibitlabs/content/ghost-series/assets/audio/ep01_vo_en.wav`
- 英文配音脚本 (粘贴到 Wink AI 配音): `~/ibitlabs/content/ghost-series/scripts/ep01_vo_en.txt`
- 中文配音脚本: `~/ibitlabs/content/ghost-series/scripts/ep01_vo_cn.txt`

## 时间轴

| 时间 | 画面 | 画外音（英） | 备注 |
|---|---|---|---|
| 0:00–0:04 | `01_hook.png` | This position does not exist. I just lost forty dollars to it. | **用你手机录的 Coinbase app 实拍替换**（如果你有）；否则用这张卡 |
| 0:04–0:09 | `02_setup.png` | My bot placed a sell order to close a long position. | — |
| 0:09–0:14 | `03_diagram.png` | *(无 VO，让图示说话 / 环境音 3-5s)* | 视觉高潮点，建议配一个轻"砰"音效 |
| 0:14–0:19 | `04_twin.png` | The long closed. The sell also opened a new short. | — |
| 0:19–0:24 | `05_api_quote.png` | Coinbase's A-P-I doesn't know a close is a close. | 红字，强调 |
| 0:24–0:29 | `06_code_bad.png` | Here's what the bot sent. No reduce_only. No close endpoint. | 代码卡停留久一些让观众读清 |
| 0:29–0:33 | `07_neither.png` | Unless you set reduce_only, or hit a special endpoint. My bot did neither. | — |
| 0:33–0:40 | `08_balance_drop.png` | So stop-loss fired. The long closed at a loss. And the ghost short kept bleeding. | **可配 K 线/余额实拍**（如有） |
| 0:40–0:43 | `09_tease.png` | I then spent twenty hours blaming the wrong things. | Hook 下一集 |

## Wink 操作顺序

1. **新建项目** → 1080×1920 竖屏，帧率 30fps
2. **导入素材**: 把 `assets/cards/ep01/` 里 9 张 PNG 批量导入
3. **导入字幕**: 菜单 "字幕" → "导入 SRT" → 选 `ep01_subtitles.srt`
4. **AI 配音**:
   - 方式 A（推荐）: 打开 Wink AI 配音，把 `ep01_vo_en.txt` 内容粘进去，选一个温和男声/女声
   - 方式 B: 先用草稿 `ep01_vo_en.wav` 对轨，后期再替
5. **时间轴排列**: 按上表把 9 张 PNG 依次排到主轨，每张停留按表里的秒数
6. **音频**: 配音轨放第二轨；音乐选 Wink 库里 lofi/minimal 类，音量 -18dB
7. **转场**: 卡片间统一用 "硬切" 或 "淡化" 0.3s（不要花哨）
8. **音效建议**: 0:09 图示出现时加一个轻微的 "whoosh" 或钢琴单音
9. **导出**: H.264, 1080×1920, 30fps, 码率 8-10Mbps

## 替换建议（提升质感）

| 原卡 | 可以替换成 |
|---|---|
| `01_hook.png` | 你手机实拍：打开 Coinbase app → Portfolio → Positions 那一屏，特写"1 contract"那一行 |
| `08_balance_drop.png` | Coinbase 账户历史曲线截图（04-19 那个下跌段） |

## 下一步

Wink 里剪完导出后，**在手机上竖屏测播一次**，确认字幕不遮关键画面。
