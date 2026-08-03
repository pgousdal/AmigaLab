# Coexistence contract

AmigaLab never assumes it is the only preservation project on a Debian host.
All owned state is namespaced under `/srv/amigalab`, `/opt/amigalab`, and
`/etc/amigalab`; environment variables use the `AMIGALAB_` prefix. A future
CommodoreLab may independently use `/srv/commodorelab`.

Standalone mode is the default. Coexist mode only enables explicitly configured
shared transport caches or services; collections, metadata, transactions, and
provenance never depend on them. `/srv/retrolab/shared` is not created by
AmigaLab in standalone mode.

Combined-host example:

```text
/srv/amigalab
/srv/commodorelab
/srv/retrolab/shared  # optional, explicitly configured only
```
