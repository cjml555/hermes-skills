# Vulnerable target catalog

Pick per lab objective; do not run all of them by default — each costs RAM.

| App | Image | Host port | Default creds | Teaches |
|---|---|---|---|---|
| OWASP Juice Shop | `bkimminich/juice-shop` | 3000 | self-registration | Broadest OWASP Top 10 + business logic; has a built-in challenge list with difficulty ratings |
| DVWA | `vulnerables/web-dvwa` + `mariadb:10` | 8081 | `admin`/`password` | SQLi, XSS, CSRF, LFI/RFI, command injection; switchable `SECURITY_LEVEL` low→impossible |
| WebGoat | `webgoat/webgoat:8.0` | 8082 | self-registration | Guided lessons, less free-form |
| WordPress | `wordpress:6` + `mariadb:10` | 8090 | set at installer | Realistic CMS surface: plugins, `wp-config.php`, `/wp-login.php` fuzzing |
| Metasploitable3 | `metacpantables/metasploitable3-ub1404` | 8000-8006 | `vagrant`/`vagrant` | Multi-service host: SSH, web, Tomcat, SMB, RMI, Oracle |
| wordlist-bench | `nginx:alpine` + mounted fixtures | 8083 | none | Fuzzing calibration: known paths return 200, unknown 404 — lets you tune match codes |

## Configuration notes

- **DVWA** wants empty reCAPTCHA keys and `SECURITY_LEVEL=low` to start; it also
  needs a MariaDB service and a volume.
- **WordPress** and **DVWA** both need DB volumes declared under `volumes:`; a
  missing entry there is a common compose failure. WordPress also benefits from
  persisting `wp-content` and `wp-config.php` so reinstalls don't start over.
- **Juice Shop**: set `NODE_ENV=e2e` for deterministic behavior.
- **Metasploitable** is deliberately full of holes — keep it on the loopback bind.
- **wordlist-bench** belongs behind a compose `profiles:` entry (e.g. `bench`) so
  it stays off in default `up` runs.

## Addressing

From the **host**, targets are `127.0.0.1:<published port>`.
From the **toolbox container**, they are the service name (`juice-shop`, `dvwa`)
on the shared bridge network. Docker service DNS is the reason the toolbox
container joins the target network rather than reaching through published ports.

Retrieve a container's IP with:

```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' pt-dvwa
```

## Follow-on targets

HTB/VulnHub machines are VMs, not containers — deploy them on a separate
libvirt/VirtualBox bridge that can reach `ptnet` if a lab exercise needs a real
OS target. Pure web/CTF work never needs this.