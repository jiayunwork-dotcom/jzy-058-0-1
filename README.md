# 活性污泥 CSTR 稳态求解服务

单级完全混合反应器（CSTR）+ Monod 动力学的**稳态核算常驻后端**。
上游设计程序通过 HTTP 提交一组工艺参数，拿回一份可复核的稳态解，
无需每次现推公式。

- 运行时：Python 3.12 + FastAPI + Uvicorn
- 存储：容器内 SQLite（WAL 模式），无需外部数据库
- 范围：仅稳态核算，仅 HTTP/JSON 接口，无网页界面、无账户体系

## 模型与判定口径

Monod 比增长速率：

```
μ(S) = μmax · S / (Ks + S)
```

无衰减项、稳态时微生物净增长恰好被出流带走（`D = μ`），反解：

```
S* = Ks · D / (μmax − D)
X* = Y · (S0 − S*)
```

冲刷（washout）边界，**绝不**把超界工况代入分式：

1. `D ≥ μmax`：冲刷，`X = 0`、`S = S0`。`D == μmax` 临界点显式处理，分母永不为零；
2. `D < μmax` 但算出的 `S* ≥ S0`（等价于非平凡解要求 `X* ≤ 0`）：同样按冲刷处理，`X = 0`、`S = S0`。

> 工程上等价表述：真实临界稀释率为 `D_c = μmax·S0/(Ks+S0)`，
> `D ≥ D_c` 即冲刷。`D ≥ μmax` 与 `S* ≥ S0` 两个分支合起来恰好覆盖整条边界。

未冲刷区返回 `μ = D`（稳态恒等式）；冲刷区 `μ` 仍按 Monod 公式在 `S = S0` 处取值
（此时 `μ < D`，长不赢稀释率），字段始终有限、不会出现负分母。

## 模块划分

| 文件 | 职责 |
| --- | --- |
| `app/kinetics.py` | Monod 动力学纯函数内核 |
| `app/solver.py` | 稳态求解 + 冲刷判定 + 稀释率区间扫描 |
| `app/validation.py` | 工艺参数/扫描区间/档名的物理合法性校验 |
| `app/schemas.py` | Pydantic 请求与响应模型（对外字段 `S0/D/mumax/Ks/Y`） |
| `app/persistence.py` | SQLite 持久化（含内置示范档播种） |
| `app/profiles.py` | 具名工况档管理服务（示范档保护等） |
| `app/api/solve.py` | `POST /solve`、`POST /scan` |
| `app/api/profiles.py` | 工况档 CRUD 与 `/{name}/solve` |
| `app/main.py` | 应用装配、生命周期、统一结构化错误信封 |
| `app/errors.py` / `app/config.py` | 错误类型 / 环境配置 |

## 快速开始（Docker）

```bash
docker build -t steady-cstr .
docker run --rm -p 8000:8000 steady-cstr
# 服务即对外可用；镜像启动时自动建库并写入内置示范档
```

健康检查：`GET http://localhost:8000/health` → `{"status":"ok"}`

本地直接运行：

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

交互式文档：`http://localhost:8000/docs`。

环境变量：`STEADY_DB_PATH`（SQLite 文件路径，默认 `./data/steady.db`）、
`STEADY_MAX_SCAN_POINTS`（单次扫描点数上限，默认 100000）。

## 接口

所有请求/响应均为 JSON。错误统一为

```json
{"error": {"code": "invalid_parameters",
           "message": "工况参数不合法: D: 必须为正数",
           "details": {"reasons": {"D": "必须为正数"}}}}
```

### 1. 单点求解 `POST /api/v1/solve`

请求：`{"D": 0.2, "S0": 200, "mumax": 0.5, "Ks": 10, "Y": 0.5}`

未冲刷响应：

```json
{"D": 0.2, "S": 6.666666666666667, "X": 96.66666666666667,
 "mu": 0.2, "washout": false, "regime": "steady_biomass"}
```

冲刷响应（如 `D = 0.5 = μmax`）：

```json
{"D": 0.5, "S": 200.0, "X": 0.0,
 "mu": 0.4761904761904762, "washout": true, "regime": "washout"}
```

### 2. 稀释率区间扫描 `POST /api/v1/scan`

请求：`{"D_start": 0.1, "D_stop": 0.6, "D_step": 0.1,
"S0": 10000, "mumax": 0.5, "Ks": 10, "Y": 0.5}`

响应：`{"count": 6, "points": [{"D": ..., "S": ..., "X": ...,
"mu": ..., "washout": ...}, ...]}`

- 网格为 `D_start + k·D_step`，区间长度是整数倍步长时终点吸附到 `D_stop`
  （吸收浮点误差）；否则最后一个不超过 `D_stop` 的格点为止，**绝不外推**；
- `D_start == D_stop` 时返回单点。

### 3. 具名工况档

| 方法/路径 | 说明 |
| --- | --- |
| `GET /api/v1/profiles` | 列出全部工况档 |
| `POST /api/v1/profiles` | 登记新档（body 含 `name`、`params`、可选 `description`）；重名 409 |
| `GET /api/v1/profiles/{name}` | 取回工况档 |
| `PUT /api/v1/profiles/{name}` | 创建或整体替换 |
| `DELETE /api/v1/profiles/{name}` | 删除（204） |
| `POST /api/v1/profiles/{name}/solve` | 直接用存档参数求稳态解 |

内置示范档 `demo_aerobic`（受保护，不可改、不可删）：

```
D=0.2 h⁻¹, S0=200, μmax=0.5 h⁻¹, Ks=10, Y=0.5
手算：S* = 10·0.2/(0.5−0.2) = 6.667；X* = 0.5·(200−6.667) = 96.667
```

任何人拉起服务即可 `POST /api/v1/profiles/demo_aerobic/solve` 核对。

## 非法输入

以下工况一律返回 `422 invalid_parameters`（多字段问题会一次性全部列出）：

- `D`、`mumax`、`Ks`、`Y` 非正（含零、负数、`NaN`、`Infinity`、布尔值、字符串）；
- `S0` 为负；
- 扫描区间 `D_start ≤ 0`、`D_step ≤ 0`、`D_stop < D_start`、点数超过上限；
- 请求体含多余/未知字段（防止拼错字段被静默忽略）。

## 并发隔离

- 求解与扫描是无状态纯计算：入参进、结果出，请求之间不共享任何可变数据；
- 工况档每次操作开独立 SQLite 连接（WAL + busy timeout），计算结果不落库，
  各档只归属各自名字；同名并发登记由主键保证恰好一个成功，其余得到 409。

## 测试

```bash
pip install -r requirements-dev.txt
pytest
```

70 个测试覆盖：

- 正常工况、`D = μmax` 临界点、`D > μmax`、`S* ≥ S0` 的冲刷、`S0 = 0`；
- 题目钉死的交叉关系：未冲刷区抬高 D 则 S↑/X↓；S0 加倍 X 近似翻倍而 S 不变；
  越过 μmax 时 X 干净归零永不为负；临界点无零分母；
- 区间扫描（含跨冲刷边界、点数上限、区间网格边界）；
- 非法输入拒绝（HTTP + 内核两层）；
- 工况档登记/取回/替换/删除、示范档保护与持久化；
- 并发求解/扫描/同名登记的隔离性。
