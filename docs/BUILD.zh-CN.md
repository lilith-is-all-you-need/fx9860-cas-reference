# 从构建记录回到代码

## 三个可以独立核对的产物

| 目标 | 源文件或附件 | 可核对的结果 |
| --- | --- | --- |
| 构建小型计算器启动器 | integrations/mapped-cas-20261116/loader 或 integrations/preview-kernel-20261117/loader | 在完整 FxStudio 中打开对应 CMake 工程并构建 Release。各自的 src/expected.h 把启动器绑到指定载荷。 |
| 改 CAS 启动或数学核心 | 两个 integrations 目录的 payload、tools/build_payload.py，以及 Release 的 giac-source-and-relink-inputs.tar.gz | 可比较实际参与构建的命令、源码与冻结对象。两个现成实机包的指纹见 evidence/builds.json。 |
| 用自己提供的原版 KhiCAS 复现历史适配 | original-khicas/kload，包含 vendored runtime、构建工程与准备工具 | 先核对原版的 SHA-256。KLoad 只为这个已知镜像准备，普通程序走通用 FlashLd。 |

## 从载荷到可安装文件

小型启动器由系统识别。镜像位于外部文件。计算器在启动时查询文件各页的位置，程序通过常驻映射逻辑访问原虚拟地址。在 4 KiB 页下，两份载荷分别占 699、701 页。按每项 4 B 计算，有效物理页地址本身分别用 2,796 和 2,804 B；另有启动器、栈、上下文和 CAS 私有池的开销。碎片化及文件操作可能影响物理放置，电脑生成的哈希和页数只描述镜像身份和布局。

复现时使用隔离的 Linux 环境及保存的 SH 大端 GCC 14.1.0 工具链。冻结的 LTO 数学对象依赖相同编译器与压缩格式。快照以 khicas-work 的相对路径保存；历史脚本使用 /root/khicas-work 下的布局。先解压到空目录检查内容，再在隔离环境中将其放到相应位置。请勿覆盖已有的工作树。编译器、系统库和宿主系统独立安装。build-plan.json 给出当时编译器和输入的摘要，commands.json 记录实际编译与链接参数。源码快照含两套数学源码、各自的 libgiac、TomMath 源码、预编译链接输入、链接脚本和实用程序。GCC、gint、fxlibc、OpenLibm 的公开源码与许可证另见 NOTICE.md。这里的构建起点是冻结输入；从空白主机完整重建所有第三方依赖仍需单独验证。

使用 python tools/relink.py --variant 699 --output 新目录 或指定 --variant 701。默认运行构建计划，追加 --run 才开始链接。701 页版需要选择预览数学归档和匹配的源码树；脚本按版本选择。链接产生 payload.bin 后，复制该分支的 loader 工程到工作目录，在副本运行 python tools/prepare_image.py 原始payload.bin 输出目录。该步骤构造 512 B 外部头，写入 KHICAS.BIN，并更新此工程副本的 src/expected.h。重新构建对应启动器，成对保存输出。

## 定位与复核

启动器主体和页处理在 loader/src。目标启动、运行时绑定和系统调用接线在 payload。699 页基线的 CAS 池为 32,768 B。701 页版沿用这个池，加入二维排版和两项核心对象修改；具体对象、测试范围和限制见 evidence/preview.json。一般项目接入时，从 SDK 的第 513 页小示例验证边界读取和退出，再逐项验证文件、回调与 MENU 生命周期。


2026-11-19 在保留的 Linux 环境分别重编运行时替换对象、重新链接两个载荷，加上 512 B 头后，两份 KHICAS.BIN 均逐字节复现历史发行摘要。原版 KLoad 的准备流程也已用匹配的原始输入重跑；该镜像由测试者自行取得。 [SHA-256](../evidence/relink-verification.json)

另做了一轮附件自包含性检查。将公开快照解压到空目录，在隔离的 Linux 挂载命名空间中把它作为唯一的 khicas-work，沿用原交叉工具链，再次调用仓库的 tools/relink.py。699 和 701 页载荷均复现同一历史 SHA-256。
