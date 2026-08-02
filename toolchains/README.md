# Amiga cross-toolchains

AmigaLab installs toolchains below `/opt/amigalab/toolchains`. `common.sh`
defines `AMIGALAB_ROOT=/opt/amigalab` and
`AMIGALAB_TOOLCHAIN=/opt/amigalab/toolchains`; override either variable (or the
compatibility variable `TOOLCHAIN_PREFIX`) before running an installer. Ansible installs the host build prerequisites and
`/etc/profile.d/amigalab.sh`; start a new shell after applying the playbook.

## m68k-amigaos-gcc

The primary C compiler is the [Amiga GCC toolchain](https://franke.ms/amiga/amiga-gcc.wiki),
whose source is available from [franke.ms](https://franke.ms/git/bebbo/amiga-gcc)
and [Codeberg](https://codeberg.org/bebbo/amiga-gcc). Follow
[`m68k-amigaos/README.md`](m68k-amigaos/README.md) to build a revision-pinned
checkout. It provides `m68k-amigaos-gcc`, binutils, and compatible C runtimes.

## VBCC, VASM, and VLINK

`install-vbcc.sh` installs an operator-supplied VBCC archive. VBCC distribution
terms are published by [vBCC](https://www.compilers.de/vbcc.html); review them
before redistributing binaries. `install-vasm.sh` and `install-vlink.sh` build
from the official [VASM](https://sun.hasenbraten.de/vasm/) and
[VLINK](https://sun.hasenbraten.de/vlink/) source archives. Pass a SHA-256
variable when using the scripts to pin and verify a release.

No Amiga ROM, Workbench disk, NDK, header, or library material is committed,
downloaded, or redistributed by AmigaLab. Provide any proprietary SDK inputs
lawfully under `/srv/amigalab/ndk` and configure the toolchain according to its
own documentation.
