# Ubuntu 24 + systemd 部署说明

## 前置条件

- 系统用户 `myf5` 已存在，项目代码与 `.env` 已就绪。
- Conda 环境 `calypsoai-demo-app` 已创建，且可执行文件路径与 unit 中一致。
- 手工启动已验证可用。

## 修改路径

编辑 [calypsoai-demo-app.service](calypsoai-demo-app.service)，将以下占位路径改为你的实际目录（若与默认相同可不改）：

- `WorkingDirectory`
- `EnvironmentFile`
- `StandardOutput` / `StandardError` 中的日志目录前缀（若改日志位置，需同步改 logrotate 文件中的路径）

## 日志目录

```bash
mkdir -p /home/myf5/logs/calypsoai-demo
chown myf5:myf5 /home/myf5/logs/calypsoai-demo
```

## 安装 systemd

```bash
sudo cp calypsoai-demo-app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now calypsoai-demo-app.service
sudo systemctl status calypsoai-demo-app.service
```

常用命令：`journalctl -u calypsoai-demo-app`（仅服务元数据/启动失败时 journal 仍有少量输出；应用主日志在下面的固定文件）。

## 安装 logrotate

```bash
sudo cp calypsoai-demo-app.logrotate /etc/logrotate.d/calypsoai-demo-app
```

手动试跑（不依赖 cron 等待）：

```bash
sudo logrotate -f /etc/logrotate.d/calypsoai-demo-app
```

日志文件：`stdout.log`、`stderr.log` 位于 `/home/myf5/logs/calypsoai-demo/`。

## OOB 与 NGINX

若使用 OOB，需保证 NGINX 在本应用之前或同时就绪；可在 unit 的 `[Unit]` 中增加 `After=nginx.service` 与 `Wants=nginx.service`（服务名以 `systemctl list-units` 为准）。
