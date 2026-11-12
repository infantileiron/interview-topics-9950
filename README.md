# 栎文研究 · 访谈议题分解

为栎文研究13人运营组把匿名访谈转为可复核的词向量、近邻与主题线索，并把人工议题名称单独留在复核版本。

## 场景

上游 `interview_corpus_202611.csv` 含480篇模拟匿名文本。团队原先手工贴标签，高频空词干扰、同议题措辞分散、主题名称没有版本。本工程替代语料核查、受控词典、向量化、主题分解与命名复核，下游研究员据此逐篇核查。无外部LLM、分词API或模型下载，不把主题当语义分类真值。

六实体：CorpusDataset语料、TermLexicon词典版本、TopicStudy方案、TopicRun运行、ThemeReview人工命名复核、Report报告。六页：议题索引、匿名语料、词典版本、分解方案、主题与近邻、人工命名。ThemeIndex和ModelSummary在总览/结果共用。

## 快速启动

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

前端 http://localhost:18224 ，API http://localhost:19224/docs ，PostgreSQL端口17724。恰好frontend/backend/worker/db/redis五服务，全健康检查；数据库/Redis/共享产物用命名卷。清理测试数据：`docker compose down -v --remove-orphans`。

| 账号 | 角色 | 权限 |
|---|---|---|
| admin@liwen.test | admin / 议题复核研究员 | 全实体、批准/退回、审计 |
| analyst@liwen.test | analyst / 语料分析员 | 导入、词典、方案、运行、人工命名提审与生成报告 |
| viewer@liwen.test | viewer / 研究观察员 | 六实体只读与批准报告下载 |

统一演示密码 `Topic2026!`。PBKDF2、JWT HS256、actor审计、错误恢复、10任务队列配额；匿名401、越权403、重复复核409。密钥由JWT_SECRET配置。

## 一天的工作剧本

1. 09:00 核查480篇匿名访谈，确认doc_id不含真实人员标识。
2. 09:05 上传interview_corpus_202611.csv，保留文件名，拒绝空文本/重复ID。
3. 09:10 检查35词受控词典与5停用词，保存2026.11-v2修订版本。
4. 09:15 配置6主题、seed2305、最多250次迭代，保存方案。
5. 09:20 Redis排队，独立worker分词、TF–IDF、余弦近邻及NMF，结果落PostgreSQL和共享JSON。
6. 09:25 查看主题词、473篇有效文档的权重及7篇隔离文档；检查真实重建误差和变化阈值标记。
7. 09:30 结合实际核查范围，为T01…逐行填写人工名称及依据；名称保存在独立复核记录，不覆盖模型结果。
8. 09:40 管理员批准后生成报告，观察员下载含人工名称、原始权重与近邻的CSV。

## 分词与TF–IDF口径

词典每次保存为新实体，包含name/version/terms/stopwords；运行保存完整快照。词项NFKC、去首尾空白和小写规范化，允许1—16个中英文字母/数字（基本汉字区），禁止重复规范词。停用词必须属于词表，全部停用导致空有效词表时拒绝。

中文采用从左到右最长词表匹配，同长度按词典序；命中停用词不计token。未匹配字母/汉字跳过并计unknown_characters，标点空白跳过。不是开放词汇通用分词器。词典覆盖不足产生的全零文档先隔离，不进入IDF分母、余弦或NMF；全部全零时worker明确失败。

TF=该词次数/该文档有效非停用token总数。有效文档数N，df为含词文档数，IDF=ln((1+N)/(1+df))+1，TF–IDF=TF×IDF。不出现的词从有效特征剔除并记录unused_terms。API/结果JSON保存vocabulary、df/idf与非零稀疏向量；有界矩阵转为NumPy稠密矩阵用于NMF。余弦近邻单独行L2归一，不包含自身；相似度保留计算值，12位舍入后同值按doc_id排序。

## NMF与展示归一

输入V为未做L2归一的TF–IDF（N×M）。W为N×K、H为K×M，固定NumPy RNG seed正值初始化，使用Euclidean乘法更新最小化Frobenius范数||V−WH||。分母加1e−12；矩阵必须非空、有限、非负且非零，主题数不超过有效文档数、有效词数与8。

至少迭代10次后，abs(前误差−当前误差)/max(前误差,1e−12)小于配置tolerance才标converged；达到max_iter仍不满足则false并保留警告。记录真实迭代数、误差历史、Frobenius及相对重建误差，不证明达到全局最优。

原始W/H完整保存在运行结果JSON，重建始终用原矩阵。主题词display_fraction=H行内占比，文档display_fractions=W行内占比，仅用于显示，未拿展示归一H替换原矩阵。CSV导出前8主题词的原始H权重、全部文档原始W权重/展示占比及近邻；完整原矩阵可从运行JSON接口GET /runs/{id}取得。

主题编号是数值因子，不是语义标签。每个编号必须有唯一1—40字人工名称才能提审；管理员批准后报告固定引用该命名版本。种子中的“访谈线索一…”是模拟研究组编号，不是自动语义判断。

## 配额与失败态

CSV列doc_id,text；至少2、最多600篇，每篇1—2000字符，最多80词、8主题、600次迭代。前端文件上限1.8MB，API字段上限1.8M字符；Nginx请求上限6MiB以容纳合法JSON编码开销。短行、空文本、重复ID、空有效词表/重复词/词表外停用词拒绝。全零语料或主题数超过有效维度时worker.failed，错误可见，不静默降低主题数。

## 技术与结构

| 层 | 技术 |
|---|---|
| 前端 | React18 / TypeScript5.7 / Vite6 / Nginx1.28 |
| 后端 | Python3.12 / FastAPI / psycopg3 / NumPy2.2.1 |
| 异步与存储 | Redis7.4、独立Python worker、PostgreSQL16 |

80职责源文件。后端src/{routes,controllers,services,models,schemas,middlewares,utils,constants,config}，前端src/{api,stores,types,components/common,hooks,pages,router,utils,constants}。业务表TEXT主键+JSON文本载荷；迁移DDL在backend/migrations/001_initial.sql。事务级advisory lock保护首次并发建表，OPENBLAS/OMP线程固定1避免并发过量与数值执行差异。

枚举：后端src/constants/enums.py角色/状态、src/constants/domain.py配额；前端src/constants/enums.ts。模型/schema/前端类型保持六实体一致。环境变量DATABASE_URL、REDIS_URL、JWT_SECRET、SEED_DEMO、TASK_MODE、ARTIFACT_DIR及端口/口令见.env.example。

Seed2305生成480篇、六种模拟议题来源、35词/5停用词，7篇故意不含受控词项。没有持久化“真值分类”供模型冒充预测。SEED_DEMO=true自动seed，自然键insert-only，不覆盖手工修改，重复不新增，失败记录日志。

前端npm ci沿用已测配套依赖锁，只改根包名；本地开发后端安装requirements并配置PG/Redis，运行uvicorn src.main:app --reload；前端npm ci && npm run dev，使用Nginx或/api开发代理。

## 边界

受控词典会遗漏未登记措辞，近邻与NMF只提供描述线索，不能证明语义分类、因果或群体结论。不同词典/样本改变TF–IDF与误差，不宜直接横比。NMF因子顺序/尺度不唯一，固定seed只保证本实现复现。Redis出队后强杀无自动重投，需要重提；JSON载荷无多人乐观锁或迁移回滚。默认账号仅本地演示。

真实容器、HTTP、手算oracle、浏览器人工命名流程与截图在批次test-artifacts/gb-2305，源码不含测试截图/日志/报告。

## License

MIT，见LICENSE。
