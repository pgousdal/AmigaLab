# Development workflow

Develop on Linux using Git, an editor, and native build tools, or use native
Amiga tools when that workflow is useful. Ansible prepares
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
FS-UAE profile. The current automated example cross-compiles on the host and
uses the emulator for target testing. M3 will also support optional compilation
inside the Amiga; neither approach excludes the other. Commit source and
reproducible build instructions to local Git and optionally Gitea or another
Git remote.

To exercise the baseline project, run `make` in `examples/hello-amiga`, then
run `scripts/test-amiga.sh`. Set `AMIGALAB_RUN_FS_UAE=1` when using
`scripts/test-amiga-build.sh` to launch the
A1200 profile after a successful build. Place the executable in
`/srv/amigalab/shared` for the supplied profiles to mount it.

These scripts distinguish build failure from emulator launch, but successful
launch is not automated functional verification. The current profiles are
placeholders requiring lawful local ROM and Workbench inputs. See the
[M3 roadmap](m3-roadmap.md) for the planned staged workflow and CI evidence model.
New M3 profiles use the validated, generated workflow documented in
[canonical emulator profiles](emulator-profiles.md); the legacy A500/A1200
files are not canonical and their migration is deferred.

## First Amiga build

1. Install AmigaLab on Debian with `make install`.
2. Run the Ansible playbook and open a new shell to load `/etc/profile.d/amigalab.sh`.
3. Enter `examples/hello-amiga`.
4. Run `make`; the output is `build/hello-amiga`.
5. Copy the executable to `/srv/amigalab/shared`, configure a licensed FS-UAE
   profile, and launch FS-UAE.
