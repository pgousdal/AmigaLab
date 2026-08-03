# Port registry

AmigaLab ports are configurable and are not assumed to be free. Defaults:

| Service | Container port | Default host port | Variable | Host exposure |
|---|---:|---:|---|---|
| Gitea HTTP | 3000 | 3000 | `GITEA_HTTP_PORT` | optional |
| Gitea SSH | 2222 | 2222 | `GITEA_SSH_PORT` | optional |
| Caddy HTTP | 80 | 80 | `CADDY_HTTP_PORT` | optional |

Ansible asserts AmigaLab-configured ports are unique. It does not inspect or
modify unrelated host applications.
