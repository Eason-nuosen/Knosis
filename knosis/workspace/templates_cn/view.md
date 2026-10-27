# 可视化知识库

知识层根目录：`$base`。目标：写一个网页 `$page`，让人在浏览器里看懂这个知识库：有哪些知识、它们怎么组织、证据如何。

## 可用的内容

$forms

计算出来的形式用命令取：`knosis knowledge graph --ws $base --view derivation`（派生图：derived_from / merged_into /
superseded_by）、`--view cards`（按对象分组的规则与公式卡片）、`--view graph`、`--view flows`；
`knosis knowledge outline --ws $base` 把大纲渲染成 markdown；`knosis knowledge trace <id> --ws $base` 看一条知识的证据链。
$request
## 要求

1. 页面要能回答：知识分几块、各讲什么（大纲）；有哪些对象、什么关系（知识图谱，画成节点和边）；某类任务怎么做
   （流程图，画成步骤与分支）；哪条知识由哪些推出、并入或替换（派生图）；每条知识的内容、形式、条件、状态和证据。
   知识库里没有的形式就不画，也不要编造；所有内容都来自上面的文件，节点、边、步骤上显示它引用的知识单元 id，
   点击能看到该单元的内容与证据。
2. 自包含、离线可用：数据直接嵌进页面，脚本、样式、图形都内联，不从网络加载任何东西（不用 CDN），用 `file://` 打开就能看。
   图可以用内联 SVG 或 canvas 自己画。
3. 知识多时要能用：搜索框按 id / 内容筛选，失效的单元（merged / stale / retracted）默认隐藏、可切换显示。
4. 推荐写一个生成脚本 `view/build.py`（读上面的文件、生成 `$page`）再运行它，这样知识更新后可以重新生成；也可以直接写 HTML。
5. 写完运行 `knosis knowledge view --ws $base --check`：它在无头浏览器里加载页面，报出加载时的 JavaScript 错误和网络资源；
   有问题就改，直到输出 OK。数据里的字段可能缺失（没有 condition、没有 evidence 等），渲染时要容错。
6. 只写 `view/` 目录；不要改 `kb/`、`evidence/` 下的任何文件，不要运行内化或 `ws` 命令。

## 验收

`$page` 存在；不从网络加载资源；加载时没有 JavaScript 错误；知识层没有被改动。最后用一两句话说明页面上有哪些视图。
