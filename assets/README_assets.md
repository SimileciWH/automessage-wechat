# assets 目录说明

这三张图片是 `detect_contact_in_results()` 用于屏幕模板匹配的锚点图。
从你的 1920×1080 屏幕截图中精确裁取，**不得缩放、不得压缩**。

| 文件名 | 内容 | 用途 |
|--------|------|------|
| contacts_label.png | 搜索下拉中灰色「Contacts」文字标签 | 定位联系人区域上边界 |
| group_chats_label.png | 搜索下拉中灰色「Group Chats」文字标签 | 定位联系人区域下边界 |
| info_button.png | 联系人行右侧的 ⓘ 圆圈按钮 | 计数联系人数量（必须恰好 1 个） |

## 如果将来图片匹配失效

原因通常是微信更新后 UI 字体/颜色略有变化。重新截取步骤：

1. 按 Cmd+F，输入任意联系人名字，等搜索结果出现
2. 用 Snipaste 截取「Contacts」文字标签那一行（只截文字，不含头像）
3. 保存为 contacts_label.png 覆盖本文件
4. 同理截取「Group Chats」标签 → group_chats_label.png
5. 截取联系人行右侧的 ⓘ 按钮 → info_button.png
6. 在脚本中适当降低 LOCATE_CONFIDENCE（如从 0.85 → 0.80）
