# monitor-agent

浏览本工程 `.memory` 下的会话 JSON（Planner / Solver）。

## 启动

```bash
cd claude-code-mini
pip install -r requirements.txt   # 已含 fastapi / uvicorn
cd monitor-agent
python server.py
```

浏览器打开：http://127.0.0.1:40000/

- 左侧（约 1/5）：`.memory` 文件树  
- 右侧：点击 `.json` 后按条展示 `HumanMessage` / `AIMessage` / `ToolMessage`（内容 + 详情）

可选环境变量：

```bash
MEMORY_ROOT=/path/to/.memory   # 默认 ../.memory（即 claude-code-mini/.memory）
MONITOR_PORT=40000
MONITOR_HOST=0.0.0.0
```
