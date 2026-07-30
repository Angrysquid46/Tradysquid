# Tradysquid Maintainer for Claude Desktop

Private local MCP bundle for maintaining the shared Tradysquid checkout.

Claude must read shared coordination state and acquire the OneDrive update lock
before any write. The extension blocks `.env`, `.git`, runtime databases,
binary files, force-pushes, arbitrary shell commands, and brokerage execution.

The packaged `.mcpb` is installed through Claude Desktop Settings > Extensions
> Advanced settings > Install Extension.
