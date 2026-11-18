# 在 fx-9860GIII 上复现实验

1. 从此仓库的 Release 选择 giac-699-calculator.zip 或 giac-701-preview-calculator.zip。解压到电脑，使用仓库的 python tools/verify_pair.py 目录 校验文件组合。也可将 Get-FileHash 的结果与 evidence/builds.json 核对。
2. 先备份计算器根目录已有的 KhiMap.g1a、KHICAS.BIN 及需要的个人数据。确认存储有足够空间放下整对文件。将同一个 ZIP 的两个计算器文件直接复制到根目录，在系统菜单中选择 KhiMap。两个版本使用相同的文件名。
3. 首先输入 2+2，应得到 4。699 页基线另做一次正常退出，再测运行中按 MENU 后直接选回。早期基线的后一个操作有人报告停在 Loading，请单独记录。
4. 对 701 页版，输入 1/2 观察分式，尝试 expand((x+1)^8)。在 F6 Options 切换输入预览和输出格式，F3 查看长结果；按 F1 对照文本。按 EXIT 退出后重新打开并计算。矩阵目前沿用括号行文，选项在下一次启动时恢复默认。
5. 回报机型、OS、两个文件的 SHA-256、操作顺序、屏幕原文、进入或退出耗时。首次启动、保存、正常退出、MENU 直接选回与先打开别的程序再返回分别记结果。

## 原版 KhiCAS

官方英文 G1A 的本次输入为 2,094,444 B，摘要见 ../evidence/original-khicas.json。用 FxProfile 普通模式生成目录，再从 FlashLd 的 Full 模式启动。已知目标 RAM 保留区为 [0x88051000, 0x8807D000)。FlashLd 请求一个合适的 OS 连续块。发生冲突时再向 OS 申请，失败后在程序目录的 RUN.LOG 中留下本次记录。No fitting OS block 表示本次候选均冲突后，OS 无法再提供所需大小。保留到第一个 RUN_END 的日志。

历史专用方案见 ../original-khicas/kload/README.zh-CN.md。它对已核实的单一原版镜像调整内存池。普通 FlashLd 保留目标镜像，超限 Giac 使用自有载荷入口，三者的运行证据分别记录。
