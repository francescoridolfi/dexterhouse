#!/bin/bash
# Egress proxy of the workspaces (CD-022, infra/workspace_images.md): Squid without cache,
# CONNECT to 443 and GET/HEAD to 80 only towards WORKSPACE_EGRESS_ALLOWLIST, everything else
# denied (TCP_DENIED in the access log, counted by the runner as runner_egress_denied_total).
set -euo pipefail
hosts="${WORKSPACE_EGRESS_ALLOWLIST:-pypi.org,files.pythonhosted.org,registry.npmjs.org,github.com,objects.githubusercontent.com,proxy.golang.org,sum.golang.org}"
hosts="${hosts//,/ }"
for host in $hosts; do
  [[ "$host" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "invalid host in WORKSPACE_EGRESS_ALLOWLIST: $host" >&2; exit 1; }
done
cat > /etc/squid/squid.conf <<CONF
http_port 3128
acl allowed_hosts dstdomain ${hosts}
acl SSL_ports port 443
acl HTTP_ports port 80
acl CONNECT method CONNECT
acl getlike method GET HEAD
http_access deny CONNECT !SSL_ports
http_access allow CONNECT allowed_hosts
http_access allow getlike HTTP_ports allowed_hosts
http_access deny all
cache deny all
cache_mem 8 MB
via off
forwarded_for delete
httpd_suppress_version_string on
access_log stdio:/var/log/squid/access.log squid
buffered_logs off
cache_log /var/log/squid/cache.log
pid_filename /run/squid.pid
coredump_dir /var/spool/squid
CONF
exec /usr/local/bin/entrypoint.sh -f /etc/squid/squid.conf -NYC
