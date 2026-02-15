# Prompt Vault (macOS Electron Rewrite)

Prompt Vault is now a macOS-only desktop app built with Electron + TypeScript + React + SQLite.

## Stack

- Desktop shell: Electron
- Main process: TypeScript + better-sqlite3 (FTS5)
- Renderer: React + Vite
- API boundary: `window.vault.*` IPC contract

## Security Notes

- Import/export paths are selected only in the main process via system dialogs.
- Renderer does not pass arbitrary filesystem paths to backend handlers.
- Production renderer uses a strict Content Security Policy.

## Development

```bash
cd prompt_vault
npm install
npm run dev
```

`npm run dev` 会直接启动 Electron 桌面窗口并启用前端热更新。
日常调试 GUI 不需要每次打包成 dmg。

如果你只想快速看当前构建效果（不打包）：

```bash
cd prompt_vault
npm run build
npm start
```

## Test

```bash
cd prompt_vault
npm run test
```

`npm run test` 会先执行 `npm rebuild better-sqlite3`，避免在执行过 `dist:mac` 后出现 Node/Electron ABI 不匹配。

Optional Electron e2e smoke test:

```bash
cd prompt_vault
E2E_RUN=1 npm run test:e2e
```

## Build macOS package

```bash
cd prompt_vault
npm run dist:mac
```

This rewrite is intentionally not backward-compatible with the previous Python implementation.
