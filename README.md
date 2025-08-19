# 订阅源合并与更新项目

本项目是一个自动化工具，用于合并多个订阅源，进行去重和自定义处理，并最终生成一个 BASE64 编码的合并后配置。该流程通过 GitHub Actions 实现定时更新。

## 功能特性

- 🔄 自动从多个订阅源获取配置
- 🧹 智能去重，避免重复站点
- ⚡ 可选的 API 延迟过滤
- 🕒 自定义缓存时间
- 📦 BASE64 编码输出
- ⏰ GitHub Actions 自动化更新

## 快速开始

### 本地运行

1. **克隆项目**
   ```bash
   git clone <your-repo-url>
   cd <your-repo-name>
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   
   复制 `.env.example` 为 `.env` 并填入你的配置：
   ```bash
   cp .env.example .env
   ```
   
   编辑 `.env` 文件：
   ```ini
   # 订阅源 URL，用英文逗号分隔
   SUBSCRIPTION_URLS="https://example.com/config1.json,https://example.com/config2.json"
   
   # 可选：自定义缓存时间
   CACHE_TIME="48"
   
   # 可选：API 超时过滤（毫秒）
   TTL="2000"
   ```

4. **运行脚本**
   ```bash
   python main.py
   ```

生成的合并配置将保存在 `merged_config.b64` 文件中。

### GitHub Actions 自动化

1. **配置 GitHub Secrets**
   
   在你的 GitHub 仓库中，进入 `Settings` > `Secrets and variables` > `Actions`，添加以下 secrets：
   
   - `SUBSCRIPTION_URLS`: 订阅源 URL（用逗号分隔）
   - `CACHE_TIME`: 缓存时间（可选）
   - `TTL`: API 超时过滤时间（可选，单位：毫秒）

2. **启用 Workflow**
   
   提交代码后，GitHub Actions 将：
   - 每 6 小时自动运行一次
   - 支持手动触发
   - 自动提交生成的 `merged_config.b64` 文件

## 配置说明

### 环境变量

| 变量名 | 描述 | 必需 | 示例 |
|--------|------|------|------|
| `SUBSCRIPTION_URLS` | 订阅源 URL 列表，用逗号分隔 | ✅ | `https://api1.com/config,https://api2.com/config` |
| `CACHE_TIME` | 自定义缓存时间 | ❌ | `48` |
| `TTL` | API 超时过滤时间（毫秒） | ❌ | `2000` |

### 功能详解

#### 1. 订阅源合并
- 支持 BASE64 编码和明文 JSON 格式
- 自动解析并合并多个配置源
- 使用第一个源作为基础模板

#### 2. 智能去重
- 基于 `api` 字段进行去重
- 保持配置的完整性和一致性

#### 3. 延迟过滤
- 当设置 `TTL` 时，自动测试每个 API 的响应时间
- 过滤掉响应时间超过设定值的站点
- 提高最终配置的可用性

#### 4. 自定义设置
- 支持覆盖缓存时间设置
- 保持原有配置结构不变

## 项目结构

```
.
├── .github/
│   └── workflows/
│       └── update.yml          # GitHub Actions 工作流
├── .env.example                # 环境变量模板
├── .gitignore                  # Git 忽略文件
├── main.py                     # 主执行脚本
├── requirements.txt            # Python 依赖
├── README.md                   # 项目文档
└── merged_config.b64          # 生成的合并配置（自动生成）
```

## 使用示例

### 基本使用

```bash
# 设置环境变量
export SUBSCRIPTION_URLS="https://source1.com/config.json,https://source2.com/config.json"

# 运行脚本
python main.py
```

### 带延迟过滤

```bash
# 设置环境变量，包含 TTL 过滤
export SUBSCRIPTION_URLS="https://source1.com/config.json,https://source2.com/config.json"
export TTL="1500"

# 运行脚本
python main.py
```

## 注意事项

1. **安全性**: 
   - 不要将 `.env` 文件提交到仓库
   - 使用 GitHub Secrets 存储敏感信息

2. **网络要求**: 
   - 确保网络可以访问所有订阅源
   - 某些源可能需要特殊的网络配置

3. **格式支持**: 
   - 支持 BASE64 编码的 JSON
   - 支持明文 JSON
   - 自动检测格式类型

4. **错误处理**: 
   - 单个源失败不会影响其他源的处理
   - 详细的日志输出帮助调试

## 常见问题

### Q: 如何添加新的订阅源？
A: 在 `SUBSCRIPTION_URLS` 环境变量中添加新的 URL，用逗号分隔。

### Q: 如何修改更新频率？
A: 编辑 `.github/workflows/update.yml` 文件中的 `cron` 表达式。

### Q: 生成的配置如何使用？
A: `merged_config.b64` 文件包含 BASE64 编码的 JSON 配置，可以直接用于相应的应用程序。

### Q: 如何调试脚本？
A: 运行脚本时会输出详细日志，包括每个步骤的处理信息和错误详情。

## 技术栈

- **Python 3.x**: 主要开发语言
- **requests**: HTTP 请求处理
- **python-dotenv**: 环境变量管理
- **GitHub Actions**: 自动化执行

## 许可证

[添加你的许可证信息]

## 贡献

欢迎提交 Issue 和 Pull Request！

---

**注意**: 请根据实际使用情况调整配置参数，确保所有订阅源都是可信的。
