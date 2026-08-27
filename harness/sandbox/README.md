# harness/sandbox · 命令沙箱

Agent 的 `bash` / `python3` 不直接在宿主机上跑，而是经本包包一层 **OS 级沙箱** 再执行。目标：

1. **工作区统一成 `/workspace`**：模型只写相对路径或 `/workspace/...`，不必知道宿主机上的 `OUTPUT_DIR`（默认 `.output`）。
2. **限制可写范围**：产物只能落到工作区（以及 `/tmp`）；系统目录只读或不可写。
3. **按环境自动选后端**：能用 bubblewrap 就用；容器里禁 user namespace 时退到 Landlock。

本包 **不是** 完整虚拟机 / 容器：不隔离网络、不限制 CPU/内存、不隐藏宿主机只读文件系统。权限 HITL、路径逃逸检查（`read`/`write`/`edit`）在 `harness/permission.py` 与 `harness/config.py` 里，与本包互补。

---

## 1. 它管什么、不管什么

| 管 | 不管 |
|----|------|
| `bash` / `python3` 子进程的 argv、cwd、可写目录 | `read` / `write` / `edit` 等文件系统工具（它们走 `OUTPUT_DIR` 前缀，不进沙箱进程） |
| `/workspace` 与宿主机 `OUTPUT_DIR` 的映射 | 网络、环境变量、密钥 |
| 超时（默认 120 秒） | 模型是否「应该」执行这条命令（那是 HITL） |

调用链：

```
模型调用 bash(command)
    → tools/bash.py 去掉 .output / 宿主机绝对路径等前缀
    → harness.sandbox.run_bash(["bash", "-c", command])
        → resolve_backend()          # auto → bwrap | landlock | off
        → wrap_argv()                # 在命令前插入 bwrap / landlock-run
        → subprocess.run(...)
```

启动时 `harness.config.ensure_runtime_dirs()` 会尝试建立 `/workspace` 链接，并打印一行状态（见 `status.py`）。

---

## 2. 三种后端

由环境变量 `SANDBOX_BACKEND` 选择（`.env` 或启动前 export）。别名见 `backend.sandbox_backend()`。

| 取值 | 实际行为 |
|------|----------|
| `auto`（默认） | 能找到 **且能跑通** 的 `bwrap` → 用 bwrap；否则有 `landlock-run` → Landlock；都没有则报错（调试可改 `off`） |
| `bwrap` / `bubblewrap` | 强制 bwrap；找不到或 user namespace 被禁则 **抛错**，不静默降级 |
| `landlock` / `ll` / `landlock-run` | 强制 Landlock |
| `off` / `0` / `false` / `no` / `none` | 软沙箱：只把 cwd 设为 `OUTPUT_DIR`，无内核限制 |

`auto` 探测 bwrap 时会真跑一次：

```text
bwrap --ro-bind / / --bind /tmp /tmp --chdir /tmp -- true
```

失败的常见原因：内核或容器（Docker、部分云主机）禁止创建 **user namespace**（`clone(CLONE_NEWUSER)`）。此时 `auto` 会改用 Landlock，不必改配置。

二进制查找顺序：`harness/bin/<name>`（可执行）→ `PATH`（`shutil.which`）。仓库自带见 [`../bin/README.md`](../bin/README.md)。

---

## 3. `/workspace` 映射（核心约定）

沙箱内的「当前目录」应对齐宿主机 **`OUTPUT_DIR`**（`harness.config`，默认项目下 `.output`）。模型侧约定：

- 写 `joke.md`、`data/a.json`，或 `/workspace/joke.md`
- **不要**写 `.output/joke.md` 或 `/home/.../claude-code-mini/.output/joke.md`

两种后端实现方式不同：

```
宿主机                          沙箱内进程看到的
OUTPUT_DIR/.output/joke.md  ←→  /workspace/joke.md   （理想情况）
```

### 3.1 bwrap：bind mount

bubblewrap 先把整棵根只读挂上，再把 `OUTPUT_DIR` **读写 bind** 到挂载点，`--chdir` 进去：

```text
bwrap
  --die-with-parent
  --ro-bind / /
  --dev /dev --proc /proc --tmpfs /tmp
  --bind <OUTPUT_DIR> <挂载点>
  --chdir <挂载点>
  -- bash -c "..."
```

- 根文件系统只读 → 改不了 `/etc`、`/usr` 等。
- `/tmp` 是独立 tmpfs，与宿主机 `/tmp` 隔离。
- `--die-with-parent`：父进程退出时子进程一起死。

**挂载点必须是宿主机上已存在的真实目录**（不能是 symlink）。原因：`--ro-bind / /` 之后，bwrap **无法在根目录 mkdir**；若 `/workspace` 是指向 `OUTPUT_DIR` 的符号链接，bind 会绑到错误目标。因此 `workspace.prepare_bwrap_mount()` 会：

1. 若 `/workspace` 是指向当前 `OUTPUT_DIR` 的 symlink → 删掉再建成真实空目录；
2. 优先用 `/workspace`；
3. 建不成（权限、已有非空目录、别人的文件）→ 退到 `/mnt/claude-code-mini-workspace`；
4. 再不行 → 报错，提示改用 `SANDBOX_BACKEND=landlock`。

`last_bwrap_mount()` 记下实际挂载点，给 `tools/bash.py` 做路径归一化：若实际不是 `/workspace`，把模型写的 `/workspace/...` 改成备用挂载点。

### 3.2 landlock：符号链接 + 内核 LSM

Landlock **不改进程根目录**，只限制「哪些路径可写」。进程仍活在宿主机命名空间里。为了让模型继续写 `/workspace`，本包尽量：

```text
/workspace  →  符号链接  →  OUTPUT_DIR
cwd = /workspace
```

`ensure_workspace_link()` 仅在 **非 bwrap** 时创建该链接：已是正确 symlink 则成功；已是别人的目录/文件/错误链接则放弃（返回 `False`），cwd 退回 `OUTPUT_DIR` 绝对路径。需要 root 或对 `/` 的写权限才能在根下建链接；容器里常失败，属预期。

`landlock-run` 命令行大致为：

```text
landlock-run
  --ro /usr --ro /lib --ro /lib64 --ro /bin --ro /sbin
  --ro /etc --ro /dev --ro /proc --ro /opt
  --rw <OUTPUT_DIR> --rw /tmp
  -- bash -c "..."
```

**故意不把 `/home` 标成只读**：`OUTPUT_DIR` 通常在 `/home/...` 下，`--ro /home` 会与 `--rw OUTPUT_DIR` 冲突。因此 Landlock 的隔离弱于 bwrap：同一用户下、不在 `--ro` 列表里的路径仍可能可写。它挡住的是往 `/etc`、`/usr` 等系统目录写。

旧内核 ABI 可能打印 `landlock-run: partial enforcement`；`tools/bash.py` 会滤掉，避免干扰模型。

### 3.3 off：仅改 cwd

`argv` 原样，`cwd=OUTPUT_DIR`。无内核限制，只适合本机调试。

---

## 4. 执行流程

```
run_sandboxed(inner, work=OUTPUT_DIR, timeout=120)
    │
    ├─ mkdir OUTPUT_DIR
    ├─ resolve_backend()
    └─ wrap_argv(inner)
           │
           ├─ off       → (inner, cwd=OUTPUT_DIR)
           ├─ bwrap     → (bwrap ... -- inner, cwd=None)   # chdir 已在 bwrap 参数里
           └─ landlock  → (landlock-run ... -- inner, cwd=/workspace 或 OUTPUT_DIR)
    │
    └─ subprocess.run(argv, cwd=cwd, timeout=120, capture_output=True)
```

便捷封装：

- `run_bash("ls")` → `["bash", "-c", "ls"]`
- `run_python("-c", "print(1)")` → `["python3", "-c", "print(1)"]`

---

## 5. 模块划分

```
harness/sandbox/
├── README.md          # 本文
├── __init__.py        # 对外 API 再导出
├── constants.py       # SANDBOX_CWD、备用挂载点、BIN_DIR
├── backend.py         # 读环境变量、找二进制、auto 探测
├── workspace.py       # /workspace 链接、bwrap 挂载点、last_bwrap_mount
├── bwrap.py           # 组装 bubblewrap argv
├── landlock.py        # 组装 landlock-run argv 与 cwd
├── runner.py          # wrap_argv / run_sandboxed / run_bash / run_python
└── status.py          # 启动日志、bash 工具前的一行状态
```

调用方请从包根导入，不要依赖子模块路径：

```python
from harness.sandbox import run_bash, prepare_sandbox_workdir, sandbox_status_line
```

| 符号 | 用途 |
|------|------|
| `SANDBOX_CWD` | 固定 `"/workspace"` |
| `sandbox_backend()` | 配置意图（可能仍是 `auto`） |
| `resolve_backend()` | 解析后的实际后端 |
| `ensure_workspace_link()` | landlock/off 下创建 `/workspace` → `OUTPUT_DIR` |
| `prepare_sandbox_workdir()` | 跑命令前准备挂载/链接，并更新 `last_bwrap_mount` |
| `last_bwrap_mount()` | 最近一次 bwrap 实际挂载点 |
| `wrap_argv` / `run_sandboxed` / `run_bash` / `run_python` | 包装与执行 |
| `sandbox_status_line()` | 如 `沙箱：landlock → 可写 …/.output；cwd=/workspace` |

---

## 6. 配置

| 变量 | 含义 |
|------|------|
| `SANDBOX_BACKEND` | `auto` / `bwrap` / `landlock` / `off`，默认 `auto` |
| `OUTPUT_DIR` | 工作区根（相对路径相对项目根），默认 `.output` |

见项目根 `.env.example`。

推荐：

- 本机、user namespace 可用 → 保持 `auto`（实际为 bwrap，隔离更强）。
- Docker / 禁 user namespace 的云主机 → `auto` 会落到 landlock；也可显式 `SANDBOX_BACKEND=landlock`。
- 调试沙箱本身 → `SANDBOX_BACKEND=off`。

---

## 7. 与其它层的边界

- **文件系统工具**（`tools/filesystem.py`）：不经过本包；路径由 `config.resolve_output_path` 限制在 `OUTPUT_DIR` 内。
- **HITL**（`harness/permission.py`）：危险命令先问人，再决定是否调用 `bash`。
- **路径归一化**（`tools/bash.py`）：去掉模型多写的 `.output/`、`OUTPUT_DIR` 绝对路径、`/workspace/`（及备用挂载点），再交给 `run_bash`。
- **记忆目录 `.memory/`**：不在沙箱工作区内，bash 默认写不进去（除非 Landlock/`off` 下路径恰好可写）。不要把会话文件当工具产物。

---

## 8. 能力与缺口（写给排障）

**能挡住（bwrap）**

- 往 `/etc`、`/usr` 等根上只读区域写入。
- 工作区外的宿主机路径（未 bind 为可写）。
- 父进程死后残留的 bash（`--die-with-parent`）。

**能挡住（landlock，强度取决于内核 ABI）**

- 往 `--ro` 列出的系统目录写入（如 `echo x > /etc/xxx` 应失败）。
- 不挡同一用户下、未列入 `--ro` 的其它可写路径（例如 `$HOME` 里 `OUTPUT_DIR` 以外的目录）。

**挡不住 / 未做**

- 出网、读宿主机只读文件（bwrap 的 `--ro-bind / /` 仍能读几乎整个根）。
- 提权、内核漏洞。
- `off` 模式下的任何内核隔离。
- `/workspace` 创建失败时的「强制统一路径」：此时 cwd 退回 `OUTPUT_DIR` 绝对路径，模型若仍写 `/workspace/...` 会找不到文件。看启动日志里 `sandbox_status_line()` 的 `cwd=`。

冒烟测试：`python tests/test_sandbox_smoke.py`（工作区可写、`/etc` 不可写）。
