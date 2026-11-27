# Templates

Sjablonen voor `scripts/new_app.py`. Niet met de hand kopiëren: gebruik de generator.
Zie [docs/apps.md](../docs/apps.md).

Placeholders:

| Placeholder | Voorbeeld (`--id agenda-plus`) |
| --- | --- |
| `__APP_ID__` | `agenda-plus` |
| `__APP_MODULE__` | `agenda_plus` (Python-module) |
| `__APP_NAME__` | `Agenda Plus` |
| `__APP_DESCRIPTION__` | Korte omschrijving |

Wijzig je een template? Werk dan ook `docs/apps.md` bij; `tests/templates/` controleert
dat bestaande apps (zoals `hello`) nog overeenkomen met de templates.
