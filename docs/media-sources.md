# Media sources and adapters

M2.3 treats ISO, ZIP, TAR, directory, and mounted-filesystem sources as
read-only. Adapters enumerate original relative paths and stream bytes without
mounting or rewriting source material. ISO inspection requires an optional
userspace reader; LHA is reported as unavailable unless an operator installs a
suitable reader.

Original media is registered separately from extracted objects. Use synthetic or
lawfully owned local paths, for example:

```sh
python3 scripts/amigalab-import.py source-add --id af-cd \
  --name 'Amiga Forever DVD' --kind iso --location /media/af.iso \
  --license-profile local-only
python3 scripts/amigalab-import.py media-scan /media/af.iso --kind iso
python3 scripts/amigalab-import.py media-import /media/af.iso \
  --source af-cd --title 'Amiga Forever DVD' --license-profile local-only --yes
```

ROM, ADF, and HDF discovery is conservative filename-based candidate reporting;
it does not claim an OS version, install media, or license rights. Discovered
files are never copied automatically into emulator profiles.
