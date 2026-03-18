# 本地静态资源（离线报告用）

本目录用于 Red Team 报告页面的**完全离线**展示，不依赖 Google Fonts / Bootstrap / Plotly 的 CDN。

## 已有内容

- **fonts/** — Inter 字体 woff2（已就绪，无外链）
- **css/inter-local.css** — Inter 本地 @font-face（仅引用 ../fonts/，无外链）
- **css/bootstrap.min.css** — 需通过下方脚本下载
- **js/plotly-2.30.0.min.js** — 需通过下方脚本下载

## 一键下载缺失的大文件（需联网执行一次）

在项目根目录执行：

```bash
./redteam-report/static/download_assets.sh
```

或在 `redteam-report/static` 下执行：

```bash
cd redteam-report/static && ./download_assets.sh
```

脚本会下载：

- Bootstrap 5.3.3 CSS → `css/bootstrap.min.css`（约 230KB，无额外外链）
- Plotly 2.30.0 → `js/plotly-2.30.0.min.js`（约 3MB+，见下方说明）

## 外链说明（文件内部是否还会连外网）

| 资源 | 是否还有外链 | 说明 |
|------|--------------|------|
| **inter-local.css** | 否 | 仅引用同目录下 `../fonts/*.woff2`，全部本地 |
| **fonts/*.woff2** | 否 | 纯字体文件，无请求 |
| **bootstrap.min.css** | 否 | Bootstrap 5 主 CSS 不含 `url()` 外链，可完全离线 |
| **plotly-2.30.0.min.js** | 视使用方式 | 仅做柱状/折线/饼图等普通图表时**无外链**；若图表类型使用 Mapbox/Geo 等地图瓦片，Plotly 会请求地图服务，需另行处理或避免使用该类图表 |

完成下载后，报告 HTML 将不再请求 `fonts.googleapis.com`、`fonts.gstatic.com`、`cdn.jsdelivr.net`、`cdn.plot.ly`。
