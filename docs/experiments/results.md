# Skutečně naměřené výsledky

Měření provedeno při implementaci dne 13. 11. 2026. Každý JSON obsahuje konfiguraci, původní scénář, prostředí, jednotlivé runy a agregace. Jde o malou demonstrační sadu, nikoli obecný výkonnostní závěr. Časy závisí na stroji a jeho zátěži.

## Přehled A–F

| Benchmark | Běhy | Úspěšné | Ostatní výsledky |
|---|---:|---:|---|
| [A](benchmark-A.json) | 12 | 11 | 1 × CONFLICT |
| [B](benchmark-B.json) | 12 | 10 | 2 × CONFLICT |
| [C](benchmark-C.json) | 12 | 10 | 2 × CONFLICT |
| [D](benchmark-D.json) | 6 | 6 | — |
| [E](benchmark-E.json) | 36 | 29 | 5 × CONFLICT, 2 × NO_PLAN |
| [F](benchmark-F.json) | 18 | 18 | — |

Celkem 96 skutečných runů, 84 úspěšných. Zamítnuté konfliktní baseline plány se nikdy nevykonaly. Vykonané kolize jsou nulové.

## A — Static MAPF, open space, 4 roboti, seeds 42–44

| Planner | Úspěch | Makespan μ ± σ | SoC μ ± σ | Planning ms μ ± σ |
|---|---:|---:|---:|---:|
| astar | 2/3 | 27.500 ± 2.500 | 63.000 ± 8.000 | 0.448 ± 0.083 |
| prioritized | 3/3 | 27.000 ± 2.160 | 63.000 ± 6.532 | 1.772 ± 0.231 |
| cbs | 3/3 | 27.000 ± 2.160 | 63.000 ± 6.532 | 2.006 ± 0.474 |
| adaptive | 3/3 | 27.000 ± 2.160 | 63.000 ± 6.532 | 1.825 ± 0.227 |

A* baseline selhala pro seed 42 kvůli konfliktu; její agregované kvality proto vycházejí ze dvou instancí. Přímé srovnání průměru s ostatními třemi instancemi by bylo zkreslené. Na těchto jednoduchých případech měly koordinované metody stejný průměrný SoC; to neznamená obecnou optimalitu prioritizovaného plánování.

## F — Online transport, 4 roboti, 12 úkolů, seeds 42–44

| Planner | Scheduler | Úspěch | Makespan μ | SoC μ |
|---|---|---:|---:|---:|
| prioritized | nearest | 3/3 | 220.667 | 595.333 |
| prioritized | priority | 3/3 | 218.667 | 593.333 |
| prioritized | hungarian | 3/3 | 219.333 | 593.333 |
| adaptive | nearest | 3/3 | 220.667 | 595.333 |
| adaptive | priority | 3/3 | 218.667 | 593.333 |
| adaptive | hungarian | 3/3 | 219.333 | 593.333 |

Priority-aware zde vykazuje mírně nižší makespan než nearest. Hungarian optimalizuje připuštěnou dávku přiřazení, nikoli celé přepravní pořadí. Rozdíly jsou malé a bez většího párovaného vzorku nelze zobecňovat.

## Celé demonstrační sklady

Samostatná integrační kontrola výchozího seed 42 (max 1 500 ticků, plánování 2 s, 2 000 CBS uzlů):

| Mapa | Prioritized | Adaptive | CBS |
|---|---|---|---|
| Small, 12 úkolů | COMPLETED, 226 ticků | COMPLETED, 226 ticků | COMPLETED, 226 ticků |
| Medium, 24 úkolů | COMPLETED, 461 ticků | COMPLETED, 461 ticků | COMPLETED, 459 ticků |
| Large, 40 úkolů | COMPLETED, 711 ticků | COMPLETED, 712 ticků | TIMEOUT v ticku 188, 13 úkolů dokončeno |

Velký online CBS run nedokazuje neřešitelnost; vyčerpal nastavený limit. Tyto end-to-end kontroly nejsou součástí 96 runů A–F. Jejich kompletní reprodukční příkaz a limity odpovídají implementačnímu plánu; při jiném zatížení stroje se okamžik timeoutu může změnit.
