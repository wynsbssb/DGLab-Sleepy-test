# 更新

- [更新](#更新)
  - [手动部署](#手动部署)

## 手动部署

只需运行这两行命令:

```bash
git pull # 拉取最新代码
pip install -r requirements.txt # 安装依赖 (如果有新的)
```

更新完成，重新启动即可.

> [!NOTE]
> 自本次更新起：
- 新增 `/recent` 接口用于按设备获取最近 24 小时的前 10 条使用记录；旧版的生成图片接口已彻底移除。
> - 仪表盘增加「状态」横向卡片（上次应用/状态/已运行时间）、带右侧图例的环形图，以及可折叠的详细应用数据列表。

> 可以 [在这](https://github.com/youyi0218/DGLab-Sleepy/commits/main/.env.example) 查看 [`.env.example`](../.env.example) 更新记录，并相应修改 `.env` 文件

