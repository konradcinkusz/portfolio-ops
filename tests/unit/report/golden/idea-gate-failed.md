# Idea gate — Delta (`delta`)

Capabilities: sync, notes.

## Products that share capabilities

| Product | Status | Shared | Share |
|---|---|---|---:|
| Alpha (`alpha`) | active | sync | 1 of 2 |
| Zeta \| the other (`zeta`) | idea | notes | 1 of 2 |

## Kernels that share capabilities

| Kernel | Shared | State |
|---|---|---|
| Core (`core`) | sync | extracted, 1 of 2 package consumers |

Feed the idea from these kernels rather than building the same thing again.

## Verdict

**Failed.** A single product already has at least half of the idea's capabilities (B6):

```text
error B6 products.yaml:26: idea 'delta' shares 1 of its 2 capabilities with product 'alpha' (sync) — merge it into 'alpha' by archiving the idea, or record an admit decision that names delta and says why it stands apart
error B6 products.yaml:26: idea 'delta' shares 1 of its 2 capabilities with product 'zeta' (notes) — merge it into 'zeta' by archiving the idea, or record an admit decision that names delta and says why it stands apart
```
