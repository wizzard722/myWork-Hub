# Beveiliging

> **Levend document.** Bij wijzigingen aan de reverse proxy, gateway, netwerken,
> firewall, het auditlog of de assistent wordt dit document bijgewerkt.

## Lagen

```
Internet
   │  alleen 80/443 open (host-firewall, nftables)
┌──▼───────────────┐
│ proxy (Caddy)    │  TLS (ook per klant-subdomein), HSTS, CSP en andere headers,
│                  │  max. uploadgrootte, verbergt servernaam
└──┬───────────────┘
   │  netwerk "edge"
┌──▼───────────────┐
│ gateway (nginx)  │  routering, echte client-IP, rate limiting (inloggen streng)
└──┬───────────────┘
   │  netwerk "internal" (geen internet)
┌──▼─────────┬──────────┬────────────┬───────────┐
│ core       │ web      │ assistent  │ app-<id>  │
└──┬─────────┘          └─────┬──────┘           │
   │  netwerk "data" (geen internet)              │
┌──▼──────────────────┐       │ alleen assistent: netwerk "egress" naar de LLM-API
│ PostgreSQL, Redis   │◀──────┘ (Redis)
└─────────────────────┘
```

| Laag | Docker Compose | Kubernetes |
| --- | --- | --- |
| Publieke ingang | `proxy` (Caddy) op 80/443 | Ingress-controller (bijv. ingress-nginx + cert-manager) |
| Interne router | `gateway` | `gateway` |
| Afscherming tussen diensten | Netwerken `edge`, `internal`, `data`, `egress` | NetworkPolicies (`base/networkpolicies.yaml`), standaard alles geweigerd |
| Host | nftables (`deploy/firewall/nftables.conf`) | firewall van de nodes/cloud |

## Reverse proxy (Caddy)

Bestand: `proxy/Caddyfile`, image `mywork-hub-proxy`.

- **TLS:** `HUB_TLS=internal` gebruikt een eigen CA (ontwikkeling, `https://localhost`
  en `https://<klant>.localhost`; de browser waarschuwt). `HUB_TLS=ondemand` vraagt per
  subdomein een Let's Encrypt-certificaat aan, maar **alleen voor bestaande klanten**:
  Caddy vraagt eerst `GET /api/core/tls/ask?domain=...` aan de core. Zo kan niemand
  certificaten laten aanmaken voor willekeurige subdomeinen.
- **HTTP → HTTPS** (308) en **HSTS** (1 jaar, inclusief subdomeinen).
- **Headers:** `Content-Security-Policy` (alleen eigen bronnen; afbeeldingen ook via
  https voor klantlogo's), `X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`, `Permissions-Policy`; `Server` en `Via` verwijderd.
- **Limieten:** uploads max. 100 MB, header-timeout 10 s.
- Admin-API van Caddy staat uit.

## Gateway (nginx)

Bestand: `gateway/nginx.conf`.

- **Echte client-IP** uit `X-Forwarded-For`, alleen van interne adressen.
- **Rate limiting per IP:** inloggen, vernieuwen, aanmelden en wachtwoord wijzigen
  10 per minuut (burst 5), overige API 50 per seconde; daarboven `429`.
  Max. 100 gelijktijdige verbindingen per IP.
- `X-Request-ID` op elke aanvraag (ook in het auditlog).

## Netwerken en poorten

- Alleen de proxy publiceert poorten (80, 443, 443/udp). Database, Redis, gateway en
  services zijn niet van buiten bereikbaar.
- `internal` en `data` zijn Docker-netwerken met `internal: true`: geen verkeer naar
  internet. Apps zitten alleen op `internal` en kunnen dus niet bij de database.
- Getest in `tests/deploy/` (configuratie) en in de CI-rooktest (echt:
  core zonder internet, app zonder database, poorten dicht).

## Host-firewall

`deploy/firewall/nftables.conf`:

```bash
sudo nft -c -f deploy/firewall/nftables.conf   # controleren
sudo nft -f deploy/firewall/nftables.conf      # toepassen
```

- Inkomend standaard **geweigerd**; open: 80/tcp, 443/tcp, 443/udp, en SSH (22) met
  limiet of alleen vanaf beheer-adressen (set `ssh_admins_v4`).
- Eigen tabel `inet mywork_hub`: de regels van Docker blijven intact.
- Poorten openzetten of sluiten: pas de sets `open_tcp` / `open_udp` aan. Houd ze gelijk
  aan de gepubliceerde poorten in `docker-compose.yml` (bewaakt door een test).

## Containers

Alle eigen images zijn gehardend op Alpine (zie [containers.md](containers.md)):
geen shell, geen package manager, geen setuid-bestanden, uid 65532, read-only
bestandssysteem, geen Linux-capabilities, `no-new-privileges`. PostgreSQL (uid 70) en
Redis (uid 999) draaien ook als niet-root, read-only en zonder capabilities.

## Geheimen

Nooit in git. Docker: `.env` (zie `.env.example`). Kubernetes: Secrets `hub-data`
(PostgreSQL/Redis), `hub-secrets` (database-URL, Redis-URL, JWT-sleutel) en `hub-llm`
(API-sleutel van de LLM), zie de productie-overlay.
