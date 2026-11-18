# fx-9860GIII · KhiCAS 与 Giac 实验参考

原版 KhiCAS 的内存共存实验，以及两个将 Giac 载荷放在外部 Flash 文件中的构建。日常使用普通 Add-in 请从 [FxProfile 和 FlashLd](https://github.com/lilith-is-all-you-need/fx_universal_loader/releases/tag/v0.2.0-beta.4) 开始。

| 版本 | 镜像 | 验证范围 |
| --- | --- | --- |
| 原版英文 KhiCAS | 2,094,444 B，512 页 | 历史 KLoad 专用适配首次启动有实机反馈。新版通用 FlashLd 在受测实机报告无法安放驻留区。 |
| [Giac 699 页基线](https://github.com/lilith-is-all-you-need/fx9860-cas-reference/releases/tag/reference-2026.11) | 2,859,236 B，KhiMap + KHICAS.BIN | RC1 首次启动有实机反馈。MENU 后直接选回曾停在 Loading。 |
| [Giac 701 页二维预览](https://github.com/lilith-is-all-you-need/fx9860-cas-reference/releases/tag/reference-2026.11) | 2,867,576 B，KhiMap + KHICAS.BIN | 两个数学核心对象有变化。主机测试及固件辅助模拟验证，等待对应构建实机验收。 |

**[下载两个独立的实机包和构建快照](https://github.com/lilith-is-all-you-need/fx9860-cas-reference/releases/tag/reference-2026.11)** · [装机与验收](docs/DEVICE.zh-CN.md) · [开发与复现](docs/BUILD.zh-CN.md) · [历史文档索引](docs/HISTORY.md)

历史专用适配器附件 original-khicas-kload.zip 需要测试者自备匹配的原版镜像；Giac 两个实机包已经分别包含完整配对文件。两份载荷本次重新链接后均匹配历史 SHA-256。[复建结果](evidence/relink-verification.json)

English: [install and test](docs/DEVICE.en.md) · [build and source map](docs/BUILD.en.md). Exact file sizes and hashes are in [the build catalog](evidence/builds.json). The two archives install the same filenames. Choose one pair at a time. The optional historical KLoad uses a different profile and a user-supplied original image. [Licenses and component provenance](NOTICE.md).
