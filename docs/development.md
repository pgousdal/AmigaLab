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
run `scripts/test-amiga.sh`. Set `AMIGALAB_RUN_FS_UAE=1` when using
`scripts/test-amiga-build.sh` to launch the
A1200 profile after a successful build. Place the executable in
`/srv/amigalab/shared` for the supplied profiles to mount it.

## First Amiga build

1. Install AmigaLab on Debian with `make install`.
2. Run the Ansible playbook and open a new shell to load `/etc/profile.d/amigalab.sh`.
3. Enter `examples/hello-amiga`.
4. Run `make`; the output is `build/hello-amiga`.
5. Copy the executable to `/srv/amigalab/shared`, configure a licensed FS-UAE
   profile, and launch FS-UAE.
