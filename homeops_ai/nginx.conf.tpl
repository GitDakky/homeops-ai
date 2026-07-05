worker_processes  1;

# Log to stderr/stdout (container-friendly)
error_log /dev/stderr notice;

events { worker_connections 1024; }

http {
  include       /etc/nginx/mime.types;
  default_type  application/octet-stream;

  # Logging (configurable via nginx_log_level option)
  __NGINX_ACCESS_LOG__
  error_log  /dev/stderr notice;

  sendfile        on;
  keepalive_timeout  65;

  # Normalise HA's X-Ingress-Path: some Supervisor versions send it with a
  # trailing slash. Concatenating "/dashboard" onto that yields a double
  # slash, which Hermes' X-Forwarded-Prefix validator rejects — the SPA
  # then falls back to root-relative asset URLs and renders a blank page.
  map $http_x_ingress_path $ingress_prefix {
    default "";
    "~^(?<p>.+?)/*$" $p;
  }

  # Ingress note: keep redirects relative so we stay under HA Ingress.

  server {
    listen 48109;

    # Web terminal (ttyd)
    # ttyd base-path is configured as /terminal (no trailing slash).
    # Some clients will hit /terminal first, so redirect to /terminal/.
    location = /terminal {
      return 302 /terminal/;
    }

    # Proxy everything under /terminal/ (including websocket /terminal/ws)
    location ^~ /terminal/ {
      # IMPORTANT: no trailing slash in proxy_pass so nginx preserves the full URI
      proxy_pass http://127.0.0.1:__TERMINAL_PORT__;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
    }

    # Landing page (shown inside HA Ingress)
    # Served as a real HTML file to avoid fragile quoting inside nginx.conf.
    # no-cache: browsers must revalidate on every load so add-on updates
    # are visible immediately (stale operator consoles caused repeated
    # "still shows old version" confusion).
    location = / {
      root /etc/nginx/html;
      default_type text/html;
      add_header Cache-Control "no-cache, must-revalidate";
      try_files /index.html =404;
    }


    # Hermes Agent dashboard UI (config, sessions, skills, and in-browser chat).
    location = /dashboard {
      return 302 /dashboard/;
    }

    location ^~ /dashboard/ {
      proxy_pass http://127.0.0.1:__HERMES_DASHBOARD_PORT__/;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      # Hermes >= v0.18 validates the Host header against its bound
      # interface (DNS-rebinding defence, GHSA-ppp5-vxwm-4cf7). The
      # dashboard binds to loopback, so we must present a loopback Host
      # — NOT $host, which carries the HA ingress hostname and gets a
      # 400 "Invalid Host header".
      proxy_set_header Host 127.0.0.1:__HERMES_DASHBOARD_PORT__;
      # Let the dashboard reconstruct prefixed URLs under HA Ingress
      # (assets, redirects). HA supplies the ingress prefix in
      # X-Ingress-Path (normalised above to strip trailing slashes);
      # the dashboard honours X-Forwarded-Prefix.
      proxy_set_header X-Forwarded-Prefix "$ingress_prefix/dashboard";
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
      proxy_buffering off;
    }

    # Local dashboard API used by the operator console.
    location ^~ /super/api/ {
      proxy_pass http://127.0.0.1:__DASHBOARD_API_PORT__/api/;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_read_timeout 30s;
      proxy_send_timeout 30s;
    }

    # Voice router health/stats (read-only) used by the landing page.
    location ^~ /router/ {
      proxy_pass http://127.0.0.1:__ROUTER_PORT__/router/;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_read_timeout 10s;
      proxy_send_timeout 10s;
    }

    # (Optional) Gateway UI via ingress has been intentionally removed.
    # See landing page link that opens the gateway in a separate tab.

    # Everything else: 404
    location / {
      return 404;
    }
  }

  __HTTPS_GATEWAY_BLOCK__
}
