# 学位论文自动审查系统

Python / FastAPI 后端与 HTML、CSS、JavaScript 前端。用于毕业论文负面清单第 2–38 条检查，支持原文定位、页面截图、人工划除和最终报告生成。

## 启动

推荐 Python 3.11。先准备一个支持 OpenAI Chat Completions 的模型服务，然后执行：

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# 按实际模型服务修改 .env，然后导出配置
set -a
. ./.env
set +a
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8088 --workers 1
```

打开 `http://127.0.0.1:8088/`。应用只使用一个 worker；模型服务单独运行。Windows 可用 PowerShell 设置同名环境变量，再运行上述 Python 启动命令。

上传论文后可填写额外评审重点。报告中勾选“划除”表示排除对应提示，底部按钮生成独立的最终报告；原始报告保留。

## 代码目录

- `app/checkers/`：文档结构、公式、引用、版面与语义检查。
- `app/evidence.py`：证据定位与原页截图。
- `app/final_report.py`：人工复核后的报告汇总。
- `app/main.py`：接口；`app/workflow.py`：任务流程。
- `app/static/`：前端页面。
- `scripts/`：测试、启动和既有运维脚本。部分运维脚本包含原部署环境路径，请按实际环境修改。
- `tests/fixtures/cross_page.pdf`：人工构造的跨页测试材料。
- `docs/`：早期需求与架构材料；当前行为以源码为准。

## 快速检查

```sh
python scripts/test_final_report.py
python scripts/test_review_focus.py
python scripts/test_semantic_coverage.py
python scripts/test_review_regressions.py
python scripts/test_evidence_api.py
python scripts/test_e2e_pipeline.py
node scripts/test_review_form.cjs
node scripts/test_evidence_ui.cjs
```

Node 仅用于前端脚本检查，运行网页无需 Node 构建。使用真实论文或在线模型的测试，需要自行提供对应材料和模型地址；源码包不包含这些数据。

## 检查范围

报告会区分发现问题、检查通过和待核对。第 7、22、25、27 条在已测论文中仍存在需要人工核对的范围，不能将所有条目都视为已自动完成。

运行数据默认保存在 `data/`，模型与接口密钥通过环境变量配置。源码包未包含真实论文、评审报告、运行日志、模型权重、密钥及旧 Git 历史。
