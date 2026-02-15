import { BrowserWindow, Menu, type MenuItemConstructorOptions } from "electron";

import type { MenuCommand } from "../shared/types";

function sendMenuCommand(command: MenuCommand): void {
  const focused = BrowserWindow.getFocusedWindow();
  if (!focused) {
    return;
  }
  focused.webContents.send("vault:menu-command", command);
}

export function installAppMenu(): void {
  const template: MenuItemConstructorOptions[] = [
    {
      label: "Prompt Vault",
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "文件",
      submenu: [
        {
          label: "新建提示词",
          accelerator: "CommandOrControl+N",
          click: () => sendMenuCommand("new"),
        },
        {
          label: "保存",
          accelerator: "CommandOrControl+S",
          click: () => sendMenuCommand("save"),
        },
      ],
    },
    {
      label: "编辑",
      submenu: [
        {
          label: "聚焦搜索",
          accelerator: "CommandOrControl+F",
          click: () => sendMenuCommand("focus-search"),
        },
        { type: "separator" },
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
    {
      label: "视图",
      submenu: [{ role: "reload" }, { role: "forceReload" }, { role: "toggleDevTools" }],
    },
    {
      label: "窗口",
      submenu: [{ role: "minimize" }, { role: "zoom" }, { role: "close" }],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}
