# Windows 下 Git “invalid path” 问题说明

## 原因

Windows 不允许在文件/目录名中使用冒号 `:`。仓库中部分路径包含时间戳目录名（如 `2025-11-13 11:30:00`），在 Windows 上无法创建，导致 `git checkout` 报错。

---

## 纯 Windows 解决方法（无需 Linux/WSL）

在当前仓库已按下面步骤配置并验证通过，可直接使用。

### 步骤 1：关闭 NTFS 路径保护并启用稀疏检出

在项目根目录执行（或已写入 `.git/config`）：

```bash
git config core.protectNTFS false
git config core.sparseCheckout true
```

### 步骤 2：排除含冒号的目录

编辑 `.git/info/sparse-checkout`，内容为（排除带时间戳的 log 目录）：

```
/*
!data/agent_data_astock_hour/
!data/agent_data/
```

### 步骤 3：检出目标分支/提交

```bash
git checkout -b haiyan 82174e5901536fe27ea54e84c26efd3e06a6eb85
```

**说明**：

- 代码和除上述两个目录外的文件都会正常检出。
- 本地**不会**有 `data/agent_data/` 和 `data/agent_data_astock_hour/` 下的内容（带冒号的 log 被排除）。
- 若以后需要这些 log，可在 WSL 或 Linux 上完整检出，或由仓库维护者把目录名改为不含 `:`（如 `2025-11-13_11-30-00`）后推送。

### 其他可选做法（仍为纯 Windows）

- **降级 Git**：部分用户反馈 Git for Windows 2.16.2 或 2.20.1 在配合稀疏检出时不会报 invalid path，可尝试安装旧版本后再按上述步骤操作。
- **只检出更早提交**：若不需要 82174e59 的改动，可在 Windows 上直接 `git checkout -b haiyan <更早的 commit>`，避开包含这些路径的提交。

---

## 其他方案（需 Linux/WSL 或改仓库）

| 方案 | 说明 |
|------|------|
| **WSL** | 在 WSL 里 clone/checkout，可完整检出含冒号的路径。 |
| **从源头改目录名** | 在 Linux/Mac/WSL 中把时间戳里的 `:` 改成 `-` 等，修改生成目录的代码后推送，一劳永逸。 |

当前仓库已用**纯 Windows 方法**成功检出分支 `haiyan`。
