# Development workflow

Develop on Linux using Git, an editor, and native build tools. Ansible prepares
`/opt/amigalab/toolchains` and the shell environment; install the GCC toolchain,
VBCC, VASM, and VLINK with the documented helper scripts and lawful inputs.

```
VS Code
  ↓
Git
  ↓
m68k compiler
  ↓
Amiga executable
  ↓
FS-UAE
  ↓
Testing
```

Build the Amiga executable on Linux, place test artifacts in
`/srv/amigalab/builds` or `/srv/amigalab/shared`, then launch the appropriate
FS-UAE profile. The emulator is used for target testing, not compilation. Commit
source and reproducible build instructions to Gitea or another Git remote.

To exercise the baseline project, run `make` in `examples/hello-amiga`, then
run `scripts/test-amiga-build.sh`. Set `AMIGALAB_RUN_FS_UAE=1` to launch the
A1200 profile after a successful build. Place the executable in
`/srv/amigalab/shared` for the supplied profiles to mount it.
