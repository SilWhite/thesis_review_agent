# 学位论文自动审查系统

检查学位论文写作负面清单第 2–38 条，共 37 项：9 项确定性、14 项版面、14 项语义检查。支持原文定位、PDF 原页截图、人工划除和最终报告。完整能力范围与限制见[需求文档](docs/需求文档.md)，模块、接口和存储见[技术方案](docs/技术方案.md)，流程见[架构图](docs/architecture.svg)。

## 启动

需要 Python 3.11+ 和单独运行的内部模型服务。应用使用一个进程、一个 worker。

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填写可信本地／内网模型地址和模型名
set -a
. ./.env
set +a
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8088 --workers 1
```

打开 http://127.0.0.1:8088/ 。接口文档：`/docs`；机器可读契约：`/openapi.json`。Windows 可通过 PowerShell 设置同名环境变量。当前没有账号权限，只允许单实例写同一数据目录。

页面使用真实模型。离线测试可通过 API 显式提交 `model_mode="mock"`：执行本地规则，跳过模型请求，结果为 partial。

部署脚本：`bash scripts/start_agent.sh`，或 `bash scripts/start_all.sh` 同时启动模型。`status.sh`、`stop_all.sh` 用于专用部署环境的状态与进程管理。`start_agent.sh` 默认监听 `0.0.0.0:8088`，本机使用时设置 `AGENT_HOST=127.0.0.1`。模型入口为 `scripts/start_single_gpu_q8.sh`、`scripts/start_vllm.sh`，实现位于 `scripts/models/`；模型路径、GPU 编号和命令位置通过环境配置，未包含权重和 GPU 运行库。

## 目录与定位

```text
app/
  main.py / api/       应用创建与 HTTP 路由
  jobs.py / workflow.py  排队、取消与 LangGraph 四节点
  config.py / schemas.py  配置与共享契约
  storage.py           本地文件存储
  model_client.py      模型 HTTP、JSON 解析及调用记录
  search.py            批准后的公开元数据查询
  documents/           PDF、DOCX、文本解析与文档树
  review/              三类检查器、语义任务及结论汇总
  evidence/            原文定位、校验与 PDF 截图
  reporting/           复核决定、最终报告及 Markdown
  static/              网页、证据展示与人工划除交互
tests/                 离线回归、前端契约、构造样本与模型评估
scripts/               应用和模型启动、状态、停止
docs/                  当前需求、技术方案与架构图
data/                  本地运行数据，不进入 Git
```

解析问题看 `documents/`；规则误报看 `review/checks/`；连接问题看 `model_client.py`；原页问题看 `evidence/`；复核冲突看 `reporting/service.py`；任务状态看 `jobs.py`。

## 验证

```sh
.venv/bin/python tests/run.py
# Node 在 PATH 时同时执行前端契约
.venv/bin/python tests/run.py --ui
# 重建两个构造 PDF
.venv/bin/python tests/fixtures/generate.py
```

默认 23 个 Python 套件，包含 UI 共 25 个。Python 测试在临时目录运行，不调用真实模型或外部搜索。`expected_*.json` 是正在使用的接口和结果契约，不能随意更新以绕过失败。最新回归 25/25 通过；构造样本测试不等于真实模型效果、GPU 性能或内网隔离验收。

需要模型实测时，配置内部模型后显式执行 `python tests/live/semantic_smoke_cases.py /tmp/semantic-results.jsonl`。该脚本使用构造材料输出观察记录，不作为默认回归或模型质量合格证明。

## 配置与数据

配置项见 `.env.example`：模型地址、名称、可选密钥、DATA_ROOT、上传大小与请求超时。上传默认 100MiB，文本 API 最多 100 万字符；当前上传错误文字仍有“30MB”提示。没有统一全文长度保护，模型默认超时 600 秒。

DATA_ROOT 默认是本目录 `data/`，保存原件、任务、报告、复核选择、最终报告快照和本地模型调用记录。调用记录含论文上下文，需与论文使用相同的访问和保留策略。当前已知限制和待完成项集中在需求文档，避免在多处重复维护。
