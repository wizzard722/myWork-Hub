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

## Auditlog

Elke handeling van beheerders (en ook inloggen, uitloggen en handelingen van de
assistent) is te herleiden. Code: `services/core/src/core/audit.py`, migratie
`0002_audit_log.py`, API `routers/audit.py`, scherm Beheer → Auditlog.

**Per regel:** tijdstip, wie (`actor_type` gebruiker/assistent/systeem, e-mail, rol),
wat (`action`, doel, details zoals oude → nieuwe waarde), uitkomst (gelukt, geweigerd,
mislukt), IP-adres (echte client-IP via proxy en gateway), user-agent en
`request_id` (zelfde ID als in de logs van proxy en gateway).

**Vastgelegde handelingen:**

| Groep | Acties |
| --- | --- |
| Inloggen | `auth.login`, `auth.login_failed` (met reden), `auth.logout`, `auth.session_reuse_detected` |
| Organisatie | `tenant.created` (aanmelding of CLI), `tenant.updated` |
| Gebruikers | `user.created`, `user.updated`, `user.role_changed`, `user.activated`, `user.deactivated`, `user.password_reset`, `user.password_changed`, `user.deleted` |
| Thema | `theme.updated` (voor en na), `theme.reset` |
| Beheertoegang | `admin.<methode> <pad>` met uitkomst `denied` als een niet-beheerder een beheerfunctie probeert |
| Auditlog | `audit.exported` |
| Assistent | `assistant.tool_call`, `assistant.tool_declined` (namens de gebruiker) |

Geweigerde pogingen (bijv. een beheerder die een eigenaar wil aanmaken) worden ook
vastgelegd, met uitkomst `denied` en de reden.

**Onveranderbaar en controleerbaar:**

- De applicatierol mag alleen `INSERT` en `SELECT` (geen `UPDATE`/`DELETE`).
- Een trigger blokkeert `UPDATE` en `DELETE` voor iedereen, ook voor een superuser.
- **Hash-keten per klant:** elke regel bevat de SHA-256 van de vorige regel plus de
  eigen inhoud. `GET /api/core/audit/verify` (knop "Integriteit controleren")
  herberekent de keten; een gewijzigde of verwijderde regel valt direct op — ook als
  iemand met volledige databasetoegang de trigger uitschakelt (getest).
- Handeling en auditregel staan in dezelfde transactie: geen handeling zonder regel.
- Row-Level Security: een klant ziet alleen zijn eigen auditlog; alleen beheerders.
- Elke regel gaat ook als JSON naar de logger `audit` (stdout), voor doorsturen naar
  een SIEM of logplatform.

**API:** `GET /audit` (filters `action`, `actor`, `outcome`, paginering
`before_id`), `GET /audit/verify`, `GET /audit/export.csv`, `POST /audit/events`
(alleen `assistant.*`, op naam van de ingelogde gebruiker).

## LLM-assistent

Service `assistant` (`services/assistant/`), achter de gateway op `/api/assistant`, paneel
in de web-schil (knop met sterretje). Staat uit zolang `ANTHROPIC_API_KEY` leeg is.

**Hoe hij werkt:** de gebruiker vraagt iets; het taalmodel (Claude, standaard
`claude-opus-5-5`, via de Anthropic API) kiest tools; de assistent voert ze uit bij de
apps en de core en geeft de resultaten terug aan het model.

**Binnen de rechten van de gebruiker:**

- **Zelfde token:** elke tool-aanroep gaat met het toegangstoken van de gebruiker naar de
  app of de core. De app controleert zelf de rechten (`mywork_sdk.current_user` /
  `require_role`); de assistent heeft nooit meer rechten dan de gebruiker.
- **Alleen toegestane tools:** tools met een hogere `min_role` dan de gebruiker worden niet
  aan het model aangeboden. Probeert het model toch een onbekende tool, dan wordt die
  geweigerd en niet uitgevoerd.
- **Bevestiging:** leesacties (GET) worden direct uitgevoerd; alle andere acties pas nadat
  de gebruiker in het paneel op **Uitvoeren** klikt. Weigeren of een nieuw bericht sturen
  annuleert de actie.
- **Invoercontrole:** invoer wordt tegen het JSON-schema van de tool gecontroleerd.
- **Prompt-injectie:** de systeemprompt behandelt inhoud uit toolresultaten als data, niet
  als opdracht; wijzigende acties vereisen bovendien altijd bevestiging door de mens.
- **Grenzen:** maximaal 8 model-stappen per beurt; conversaties 24 uur in Redis, alleen
  terug te vinden door de gebruiker die ze begon.
- **Auditlog:** elke uitgevoerde, mislukte of geweigerde actie komt als
  `assistant.tool_call` / `assistant.tool_declined` in het auditlog van de klant, op naam
  van de gebruiker met `actor_type = assistant`.

**Gegevens naar de LLM-aanbieder:** berichten van de gebruiker en de resultaten van tools
gaan naar de Anthropic API. Zet de assistent alleen aan als de klant daarmee akkoord is
(verwerkersovereenkomst). Netwerk: alleen de assistent zit op het `egress`-netwerk; core,
apps en databases kunnen niet naar internet.

**Instellingen:** `ANTHROPIC_API_KEY`, `HUB_LLM_MODEL` (standaard `claude-opus-5-5`),
`HUB_LLM_EFFORT` (standaard `medium`), `HUB_LLM_MAX_TOKENS`, `HUB_MAX_STEPS`,
`HUB_REDIS_URL`, `HUB_CORE_URL`. Bij een weigering door de veiligheidsfilters van het model
wordt automatisch een ander model gebruikt (server-side fallback); prompt-caching staat aan.
