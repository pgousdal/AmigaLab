# AmigaLab
### A Reproducible Amiga Preservation & Development Workstation

> **AmigaLab** is an Infrastructure-as-Code project that transforms a modern Debian system into a complete Amiga software preservation, development, and testing workstation.

The project aims to preserve the Amiga ecosystem while providing a modern development environment using cross-compilers, emulation, version control, automation, and reproducible infrastructure.

---

# Goals

- Preserve classic Amiga software
- Maintain a complete Aminet mirror
- Cross-develop Amiga software from Linux
- Test software across multiple Amiga models
- Preserve documentation and SDKs
- Archive source code and development tools
- Rebuild the entire workstation from Git
- Operate completely offline after initial setup

---

# Philosophy

Modern tools.
Classic platform.

Everything except copyrighted software should be reproducible from source and Infrastructure as Code.

A fresh Debian installation should become a fully configured Amiga workstation by running a single Ansible playbook.

---

# Features

## Preservation

- Complete Aminet mirror
- Fred Fish archive
- Documentation archive
- NDK documentation
- ROM Kernel Manuals
- Magazine cover disks
- Demo scene archive
- Public domain software
- Local search index

---

## Development

- m68k-amigaos-gcc
- VBCC
- VASM
- VLINK
- GNU Make
- CMake
- Python
- Git
- VS Code
- GitHub CLI

---

## Emulation

Multiple FS-UAE profiles:

- Amiga 500
- Amiga 600
- Amiga 1200
- Amiga 3000
- Amiga 4000

Supporting:

- Kickstart 1.x
- Kickstart 2.x
- Kickstart 3.x
- AmigaOS 3.2

---

## Networking

Optional services:

- Gitea
- Caddy
- Samba
- SSH
- Meilisearch
- File Browser
- FTP
- NFS

---

## Archive

Designed to store:

- Aminet
- WHDLoad
- HDF images
- ADF images
- Development tools
- SDKs
- Documentation
- Source code
- Personal projects

---

# Architecture

```
                    Debian

             +-------------------+
             |      Ansible      |
             +-------------------+
                      |
                      |
      +---------------+----------------+
      |                                |
      |                                |
 Docker Services                 Native Packages
      |                                |
      |                                |
 Gitea                        Cross Compilers
 Meilisearch                  FS-UAE
 Caddy                        Git
 Homepage                     Build Tools
      |
      |
      +------------+
                   |
             Amiga Development
                   |
      +------------+-------------+
      |                          |
 Preservation               Cross Development
      |                          |
      +------------+-------------+
                   |
                FS-UAE
                   |
             Test Workbench
```

---

# Repository Layout

```
amigalab/

├── ansible/
│   ├── playbooks/
│   ├── roles/
│   ├── inventory/
│   └── group_vars/
│
├── docker/
│   ├── compose.yaml
│   ├── caddy/
│   ├── gitea/
│   ├── meilisearch/
│   └── homepage/
│
├── fs-uae/
│   ├── A500.fs-uae
│   ├── A1200.fs-uae
│   ├── A3000.fs-uae
│   └── A4000.fs-uae
│
├── scripts/
│   ├── sync-aminet.sh
│   ├── update-whdload.sh
│   ├── build-toolchains.sh
│   ├── backup.sh
│   └── verify.sh
│
├── docs/
│
├── toolchains/
│
├── assets/
│
├── Makefile
│
└── README.md
```

---

# Infrastructure as Code

The workstation is fully reproducible.

```
Install Debian

↓

Clone repository

↓

Run bootstrap

↓

Run Ansible

↓

Machine configured

↓

Restore archives

↓

Ready to develop
```

No manual configuration should be required.

---

# Storage Layout

```
/srv/amigalab/

├── aminet/
├── whdload/
├── adf/
├── hdf/
├── kickstarts/
├── workbench/
├── ndk/
├── docs/
├── magazines/
├── fish/
├── demos/
├── source/
├── builds/
├── backups/
└── shared/
```

---

# Cross Development Workflow

```
VS Code

↓

Git

↓

Cross Compiler

↓

Amiga Executable

↓

FS-UAE

↓

Testing

↓

Commit
```

No compilation occurs inside the emulator.

The emulated Amiga is used as authentic hardware for testing.

---

# Services

| Service | Purpose |
|----------|---------|
| Gitea | Local Git server |
| Meilisearch | Archive search |
| Caddy | Web server |
| Samba | File sharing |
| SSH | Administration |
| File Browser | Web file management |

---

# Documentation

The workstation is intended to become a complete offline Amiga reference library.

Examples include:

- ROM Kernel Manuals
- AutoDocs
- NDK
- Hardware manuals
- Guru Books
- Developer magazines
- Programming guides

---

# Backups

Backups include:

- Git repositories
- Emulator configurations
- Workbench installations
- Personal projects
- Build artifacts
- Docker volumes

Large archives (Aminet, WHDLoad, etc.) can be mirrored again if needed.

---

# Future Goals

- Continuous Integration
- Automatic Aminet synchronization
- Automatic toolchain updates
- Build Open Source Amiga software
- Build OpenVN Amiga runtime
- BBS development environment
- Demo scene archive
- Classic networking experiments
- Build dashboard
- Package verification
- Preservation reports

---

# Project Principles

- Infrastructure as Code
- Open Source first
- Reproducible builds
- Offline-first
- Preservation over convenience
- Document everything
- Automate everything
- Version control everything

---

# License

MIT License

Copyright © 2026

---

*"Preserving the past with the tools of the future."*
