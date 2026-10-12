# RUR1BIDX_OPEN

RUR1 BIDX 随附第三方组件的对应源码、必要修改及构建材料。
本仓库不包含 RUR1 BIDX 的独立业务程序、客户资料、数据库、密钥、模型权重或原应用的 Git 历史。

各组件继续使用自己的许可证。没有把这些组件统一改成 GPL，也没有把整个 RUR1 BIDX 重新授权为开源软件。

## 获取对应源码

`source-catalog.json` 将组件及准确版本对应到源码文件、原始下载地址和 SHA-256。
本仓库 Releases 同时提供经过校验的源码集合；文件名和目录保持目录清单中的对应关系。

也可使用 Python 3.11 或更新版本取回选定组件的源码：

```sh
python fetch_sources.py --catalog source-catalog.json --list
python fetch_sources.py --catalog source-catalog.json --component COMPONENT_NAME --destination ./sources
python fetch_sources.py --catalog source-catalog.json --group GROUP_NAME --destination ./sources
```

请用 `--list` 输出的名称选择组件。脚本逐文件验证 SHA-256，不执行下载的源码或构建脚本。
原始下载不可用或源码是按固定 Git 提交自行归档时，脚本自动从 Releases 源码集合中取回，
同时核对集合及其中目标文件的 SHA-256。集合缓存在目标目录的 `.source-bundles/`；
只读取所需的普通文件，不展开归档中的链接或执行其内容。
源码包内的版权、许可证、发行版补丁和构建规则是适用条款的原始依据。
软件包元数据里的许可名称用于索引，不替代逐文件许可，也不是组合分发合规证明。

## RUR1NINFER

现有引擎 1.0.1 的对应源码保留在独立仓库的
[codex/engine-1.0.1-source 分支](https://github.com/hyz615/RUR1NINFER/tree/codex/engine-1.0.1-source)。
该分支记录交付二进制、源码快照、构建环境和许可证范围；默认开发分支及运行引擎没有因本次源码披露而替换。
GPL FFmpeg 与 CUDA 的具体组合分发条件另见该分支 `distribution/engine-1.0.1/LEGAL_REVIEW.json`；
源码可获取不代表该问题已经获得法律定性。

## 构建与范围

见 `BUILDING.md`、各组件的构建说明和 `SOURCE_SCOPE.md`。
`EXPORT.json` 是本次明确允许公开的仓库文件清单及校验值；上游源码集合以 Release 资产提供，避免把应用历史混入公开库。

新增的源码下载工具及目录说明采用 Apache-2.0（见 `LICENSES/Apache-2.0.txt`）。
Collabora 构建适配器和品牌文件的许可见其文件头；其余上游代码的许可证保持不变。
