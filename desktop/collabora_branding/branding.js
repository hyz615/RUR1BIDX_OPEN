// SPDX-License-Identifier: MPL-2.0
// This Source Code Form is subject to the Mozilla Public License, v. 2.0.
// See https://mozilla.org/MPL/2.0/.
// 在线编辑器的产品外观。coolwsd 的编辑页（cool.html）末尾按上游约定引用 /browser/<版本哈希>/branding.js，
// 工作台的反向代理（tmpui/backend/collabora_proxy.py，规则在 config/collabora_runtime.json 的 branding）
// 用这个文件应答，并把下面 productName 的占位符换成 config/product.json 的产品名。
// 它在 global.js 之后、编辑器主程序（延迟加载）之前运行：只改界面全局量，不改编辑器本身。
(function () {
  "use strict";
  var productName = "{{PRODUCT_NAME}}";
  if (productName) {
    // 载入进度、对话框标题、快捷键说明里的产品名。
    window.brandProductName = productName;
  }
  // 不弹欢迎页，帮助里也没有“最新更新”。
  window.enableWelcomeMessage = false;
  window.autoShowWelcome = false;
  // 没有“发送反馈”，也不在打开若干文档后请人评分。
  window.feedbackUrl = "";
  window.autoShowFeedback = false;
  // 不提示“服务器需要更新”。
  window.allowUpdateNotification = false;
  // 去掉“关于”对话框（上游约定：没有 #about-dialog 时，帮助选项卡和菜单都不放“关于”）。
  var about = document.getElementById("about-dialog");
  var holder = about && about.closest("dialog");
  if (holder) {
    holder.remove();
  } else if (about) {
    about.remove();
  }
})();
