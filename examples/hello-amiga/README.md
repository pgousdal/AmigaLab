# Hello Amiga

This is a minimal Amiga command-line executable built on Linux with
`m68k-amigaos-gcc`. With the toolchain profile loaded, run:

```sh
make
```

The artifact is `build/hello-amiga`. Copy it to `/srv/amigalab/shared` (or a
mounted Workbench volume) before launching an FS-UAE profile. The build relies
on the C runtime supplied by the installed GCC toolchain; no SDK is included in
this example.
