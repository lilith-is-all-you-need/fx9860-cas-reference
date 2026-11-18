# Development records / 实验索引

| 问题 | 当时的记录与现在的结论 |
| --- | --- |
| 原版镜像多大，为什么需考虑 RAM 共存？ | [早期分析](../history/original-khicas-investigation.zh-CN.md)讨论 160 KiB RAM 原型。现行普通 FlashLd 直接映射文件，目标私有池仍影响驻留区选址。[当前通用手册](https://github.com/lilith-is-all-you-need/fx_universal_loader/blob/main/probes/storage-loader/FOLDERS.zh-CN.md) |
| 哪些结果来自实机？ | [首次启动及重入反馈](../history/first-launch-and-reentry.en.md)，以及 [按镜像区分的实验目录](../evidence/builds.json)。原版 KLoad、699 页基线、通用 FlashLd 运行的是三条不同路径。 |
| 699 页版最初如何操作？ | [历史操作说明](../history/giac-699/先读我.txt)。[数学核心与内存测量的开发记录](../history/giac-699/开发记录.zh-CN.md)。本版对应 2,859,236 B 外部镜像。 |
| 两处 RC2 名称为什么不同？ | 老 Loader 工程把一个 10,024 B 的重入修订也称为 RC2，它配 699 页旧镜像。Giac 工程正式保存的 KHIMAP-RC2 压缩包配 701 页新镜像、9,860 B 启动器。本仓库两份安装包按页数命名。[699 页重入修订记录](https://github.com/lilith-is-all-you-need/fx_universal_loader/blob/main/large/probes/extended-cas/VALIDATION-REENTRY-20261117.json) |
| 二维版修改了什么？ | [历史技术说明](../history/giac-701-preview/技术与验证说明.md)、[操作说明](../history/giac-701-preview/先读我.txt)、[最终测试摘要](../evidence/preview.json)。页面呈现、数学核心、分配失败和取消分别测试。 |
| 如何使用现代 SDK 写自己的超限程序？ | [FxStudio 第 513 页源码示例](https://github.com/lilith-is-all-you-need/fx-9860giii-sdk/tree/main/sdk/examples/oversized-loader)，以及[普通加载选择指南](https://github.com/lilith-is-all-you-need/fx-9860giii-sdk/blob/main/docs/LOADER-SUITE.zh-CN.md)。 |

Historical reports reflect their own dates and launchers. Use the current manuals and the SHA-256 catalog to select an installable pair. An emulator pass or an earlier MENU test on another build carries its original scope.
