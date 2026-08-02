# m68k-amigaos-gcc

Use the Amiga GCC toolchain to provide `m68k-amigaos-gcc`. Its primary source
repository is <https://franke.ms/git/bebbo/amiga-gcc>; Codeberg mirror and issue
tracker: <https://codeberg.org/bebbo/amiga-gcc>.

Pin a reviewed commit before building so the result is repeatable:

```sh
git clone https://franke.ms/git/bebbo/amiga-gcc.git
cd amiga-gcc
git checkout <reviewed-commit>
make
```

Follow the upstream project's installation instructions to install beneath
`/opt/amigalab/toolchains`, or expose its `bin` directory through that prefix.
AmigaLab's profile script already adds `/opt/amigalab/toolchains/bin` to `PATH`.
The upstream project determines which runtime and headers it builds; do not copy
or download proprietary Amiga NDK material through this repository.
