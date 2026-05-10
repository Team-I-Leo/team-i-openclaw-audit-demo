# OpenCLAW Integration

This directory documents and scaffolds the OpenCLAW layer for the Team-I demo.

The runnable Python backend exposes governed audit tools at:

```text
POST /api/openclaw/tools/{action_name}
```

The TypeScript plugin scaffold under `plugins/aer_audit_tools` shows how the same tools are registered through OpenCLAW's plugin SDK. On the current HPC2 login environment, Node package execution may be restricted, so the demo runtime keeps the audited tool execution in the Python backend while preserving OpenCLAW-compatible tool contracts and agent/action schemas.

The intended OpenCLAW architecture is:

```text
OpenCLAW Agent
  -> model-backed reasoning turn
  -> registered governed audit tool
  -> Python audit backend action
  -> structured observation
  -> trajectory replay / Evidence Passport
```
