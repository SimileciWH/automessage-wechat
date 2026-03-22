# assets 目录说明

这四张图片是 `detect_contact_in_results()` 用于屏幕模板匹配的锚点图。
从你的 1920×1080 屏幕截图中精确裁取，**不得缩放、不得压缩**。

| 文件名 | 内容 | 用途 |
|--------|------|------|
| contacts_label.png | 搜索下拉中灰色「Contacts」文字标签 | 定位联系人区域上边界 |
| group_chats_label.png | 搜索下拉中灰色「Group Chats」文字标签 | 定位联系人区域下边界（有群聊时出现） |
| internet_search_label.png | 搜索下拉中「Internet search results」文字标签 | 定位联系人区域下边界（无群聊时出现） |
| info_button.png | 联系人行右侧的 ⓘ 圆圈按钮 | 计数联系人数量（必须恰好 1 个） |

> `group_chats_label.png` 和 `internet_search_label.png` 两张可选其一存在，
> 代码会自动取最近的那个作为 Contacts 区域下边界。
> 建议两张都截取放入，适应不同搜索场景。

## 截取步骤（首次配置）

1. 按 Cmd+F，输入一个**有单独联系人结果**的名字，等搜索结果出现
2. 用 Snipaste 截取以下区域（只截文字/图标本身，不含多余留白）：
   - `contacts_label.png` — 「Contacts」灰色标签文字那一行
   - `info_button.png` — 联系人行右侧的 ⓘ 圆圈按钮
3. 再分别触发两种下边界场景：
   - 搜索有群聊结果时，截取「Group Chats」标签 → `group_chats_label.png`
   - 搜索无群聊结果时，截取「Internet search results」标签 → `internet_search_label.png`

## 如果将来图片匹配失效

原因通常是微信更新后 UI 字体/颜色略有变化。重新截取并覆盖对应文件，
如仍不稳定，在脚本中降低 `LOCATE_CONFIDENCE`（如从 0.85 → 0.80）。
