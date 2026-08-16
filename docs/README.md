# Docs assets

| File | Description |
| --- | --- |
| [STATUS.md](STATUS.md) | Done / not-done checklist |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Mermaid system + pipeline diagrams |
| [out/pipeline.png](out/pipeline.png) | G-code → sim → Uno flow |
| [out/system.png](out/system.png) | Laptop → Uno → shield → sleds |
| [out/square_paper.png](out/square_paper.png) | Example paper preview (square) |
| [out/hi_paper.png](out/hi_paper.png) | Example paper preview (“hi”) |

Regenerate Graphviz PNGs:

```bash
dot -Tpng docs/pipeline.dot -o docs/out/pipeline.png
dot -Tpng docs/system.dot -o docs/out/system.png
```
