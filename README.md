# 轮组跳动相位校正

轮组校正工位导入按气嘴零点采集的侧向跳动扫描。后台用带复测标签的历史轮组拟合校正模型，在独立轮组上对照傅里叶与裸角度特征，再为待测扫描给出峰值角、复测窗口和探针尖峰核查位置。

| 模块 | 业务产出 |
|---|---|
| 轮组扫描台账 | CSV 导入、测点校验、轮组分区与导入校验和 |
| 傅里叶校正配置 | 谐波阶数、岭惩罚、复测角半径和优先复测阈值 |
| 相位峰与复调提案 | 整组留出误差、冻结系数、待测复测窗口和缺测角区 |
| 复测交班签核 | 负责人决定、签核备注和获批结果表 CSV |

## 启动与账号

在项目目录执行。

```bash
cp .env.example .env

docker compose build backend
docker compose up -d --no-build --wait
docker compose ps
docker compose exec -T backend python -m scripts.seed_demo
```

| 服务 | 用途 | 本机地址 |
|---|---|---|
| `backend` | FastAPI 业务、登录、签核和导出 | `http://127.0.0.1:19430/api` |
| `worker` | Python 3.11 异步计算 | Compose 内网 |
| `db` | PostgreSQL 16 台账、运行、签核和审计 | `127.0.0.1:17930` |
| `redis` | Redis 7 作业通知和 worker 心跳 | Compose 内网 |

Compose 项目名为 `yangyang-wheel-phase`。API 文档位于 `http://127.0.0.1:19430/api/openapi.json`。`.env.example` 包含 `COMPOSE_PROJECT_NAME`、`BACKEND_PORT`、`DB_PORT`、`SEED_DEMO`、`JWT_SECRET`。`SEED_DEMO=true` 时启动导入演示台账，手工执行 seed 可核对行数与校验和。内网 PostgreSQL 连接与 Redis 地址分别由 `DATABASE_URL` 和 `REDIS_URL` 配置。

| 角色 | 邮箱 | 演示密码 | 权限 |
|---|---|---|---|
| 分析员 `analyst` | `analyst@demo.local` | `Demo-2611!` | 导入、提交运行、查看计算和下载获批结果 |
| 复核负责人 `admin` | `admin@demo.local` | `Demo-2611!` | 分析员权限、签核和审计查询 |
| 查阅员 `viewer` | `viewer@demo.local` | `Demo-2611!` | 查看台账和获批运行、下载获批结果 |

## API 工作流

业务接口使用 `Authorization: Bearer <access_token>`。先通过 `POST /api/auth/login` 提交 `email` 和 `password`。

| 操作 | 请求 | 说明 |
|---|---|---|
| 查看列与参数 | `GET /api/spec` | 获取 CSV 列和顺序、运行参数范围及业务模块 |
| 导入扫描 | `POST /api/datasets` | JSON 对象包含 `name` 和 `csv`，`csv` 值为完整 CSV 文本 |
| 获取演示台账 | `GET /api/datasets` | seed 台账名为 `20261125-轮组跳动扫描.csv` |
| 提交计算 | `POST /api/runs` | 传 `label`、`dataset_id` 和可选的 `settings` 对象，返回 HTTP 202 和运行编号 |
| 查看计算 | `GET /api/runs/{id}` | 等待 `status` 变为 `completed`，结果里的 `tables` 列出表键和行；`failed` 时查看 `error` |
| 复核签核 | `POST /api/runs/{id}/review` | 由 `admin` 提交如 `{"decision":"approved","note":"已核对跨零角区与探针峰"}`，每次完成运行可签核一次 |
| 下载正式 CSV | `GET /api/runs/{id}/export/{key}` | 签核 `approved` 后可下载，查阅员只可取得已获批运行 |

正式 CSV 的业务表键为 `recheck_proposals`（复调提案）、`holdout_comparison`（留出误差）、`holdout_points`（测点对账）和 `model_coefficients`（冻结系数）。例如在获批后执行下列命令，`viewer_token` 和 `run_id` 分别取查阅员登录令牌和运行编号。

```bash
curl --fail-with-body -sS \
  -H "Authorization: Bearer ${viewer_token}" \
  "http://127.0.0.1:19430/api/runs/${run_id}/export/recheck_proposals" \
  -o recheck-proposals.csv
```

角色、运行状态与复核决定定义于 `backend/src/constants/workflow.py`，并用于登录响应、鉴权、运行查询和签核响应。扫描分区定义于 `backend/src/domain/records.py`，用于导入校验和训练、留出、待测分流。

## 本地开发与独立校验

领域入口在 `backend/src/domain/project.py`，由 `backend/src/services/catalog.py` 和 `backend/src/services/execution.py` 调用。HTTP 开发可从 `backend/` 安装 `requirements.txt`，配置 PostgreSQL 和 Redis 连接后，分别启动 `python -m uvicorn src.main:app --port 19430` 与 `python -m src.worker`。

只校验领域模块时，从本批根目录执行下列命令。校验脚本自动定位项目，依赖 Python 3.11+ 标准库。

```bash
python3 test-artifacts/yangyang-wheel-phase/tests/oracle.py -v
```

CSV 输入规则、误差口径和复测交班示例见 [BUSINESS.md](BUSINESS.md)。
