# OpenCLAW 集成说明

本目录用于记录和组织 Team-I 演示系统中的 OpenCLAW 集成层。

可运行的 Python 后端通过以下接口暴露受控审计工具：

```text
POST /api/openclaw/tools/{action_name}
```

`plugins/aer_audit_tools` 目录下的 TypeScript 插件脚手架展示了同一组审计工具如何通过 OpenCLAW 插件 SDK 注册。演示运行时由 Python 后端执行实际受控工具，同时保留 OpenCLAW 兼容的工具契约、智能体配置和动作模式。

OpenCLAW 集成架构如下：

```text
OpenCLAW 智能体
  -> 模型推理回合
  -> 已注册的受控审计工具
  -> Python 审计后端动作
  -> 结构化观察结果
  -> 轨迹回放 / 证据护照
```
