# Stresový test skladu 64 × 64

Uložený běh „zkouška generování složitého skladu“ měl 17 robotů, 200 přeprav a dva jednobuněčné průjezdy v řádcích 6 a 38 (počítáno od nuly). Seed byl 3318493664. Běh se zastavil na kroku 353 po 30 krocích bez pohybu, obsluhy nebo nabíjení. Dokončil 1 z 200 přeprav. Kontrola zamítla 4 200 návrhů pohybu, ke kolizi nedošlo. Nejnižší stav baterie byl 39,2 %. [Uložený stav](live-failure.json) · [Scénář](scenario.json)

Přesné přehrání použilo původní váhy `nn-a0a0d5fb69a7` a průběžné učení v oddělené databázi. Obsazení buněk, stavy všech robotů a přeprav, počet zamítnutých návrhů a identifikátory vah souhlasily s uloženým během. U průjezdu v řádku 38 se R-11 na (32, 38) a R-14 na (33, 38) opakovaně snažili vyměnit si místa. Po odmítnutí výměny oba upřednostnili čekání před ústupem. Za dvojicí čekaly další roboty. U druhého průjezdu síť zvolila čekání jako první možnost i pro jediného robota v jeho okolí, R-03. [Skóre rozhodnutí na začátku a na konci zastavení](replay.json)

Běžící kopie serveru se stejným výchozím modelem při rychlosti 16× dosáhla stejného výsledku. Klient dostal 355 různých stavových zpráv přes WebSocket včetně koncového stavu. Všech 50 kontrol dostupnosti během jízdy i kontrola po zastavení vrátily HTTP 200. Do koncového stavu běh na tomto stroji dospěl za 13,0 sekundy. [Záznam běhu přes API](http-16x.json)

Dalších 12 běhů mělo stejnou velikost 64 × 64 a 200 přeprav. Všechny používaly pevné váhy `nn-6a76bd3c5cfa`, tedy verzi po nahlášeném běhu. U změněných parametrů průjezdů nebo provozu generátor znovu vytvořil mapu i přepravy z daného seedu. Jde o srovnání konfigurací, při kterém se mohlo změnit i konkrétní zadání přeprav. Pro každý běh platil limit 4 000 logických kroků.

| Konfigurace | Roboti | Hotové přepravy | Krok zastavení |
| --- | ---: | ---: | ---: |
| Přesný uložený scénář s pevnými váhami | 17 | 5/200 | 382 |
| Dva průjezdy široké 2 buňky | 17 | 36/200 | 849 |
| Dva průjezdy široké 3 buňky | 17 | 15/200 | 453 |
| Tři průjezdy široké 3 buňky | 17 | 58/200 | 1 419 |
| Dva jednobuněčné průjezdy, přepravy jedním směrem | 17 | 16/200 | 562 |
| Otevřený sklad bez dělicí příčky | 17 | 191/200 | 2 925 |
| Šest variant s úzkými nebo širšími průjezdy či bez příčky | 32 | 0/200 v každé | 30 v každé |

Všech 12 běhů skončilo na limitu 30 kroků bez pokroku a všechny měly nula kolizí. Širší průjezdy v testovaných konfiguracích pomohly dokončit více přeprav s 17 roboty. Žádná konfigurace nedokončila všech 200. [Výsledky po jednotlivých mapách](stress-results.json)

Na testované variantě s 32 roboty prošlo kontrolou energie, nosnosti a dostupnosti všech 6 400 dvojic robot–úkol. Každý robot měl přesto vyšší skóre pro nečinnost než pro kterýkoli úkol. Například R-01 měla nejlepší přeprava skóre 1,52, čekání 8,51. Při jednorázovém přepočtu stejných kandidátů stačilo v jediném vstupu sítě zaměnit velikost flotily z 32 na 17. Úkolu pak dalo přednost 32 z 32 robotů místo nuly. Tento přepočet jen měří vliv vstupu. Síť při původním tréninku dostávala v procedurálních mapách flotily s 3 až 12 roboty. [Měření startu podle velikosti flotily](dispatch.json) · [Přepočet skóre](fleet-feature-probe.json)

Pro opakování dvanácti běhů s pevnými váhami spusťte z kořene projektu:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --directory apps/backend python \
  ../../scripts/stress-neural-warehouse.py \
  --scenario ../../docs/experiments/neural-max-stress/scenario.json \
  --checkpoint ../../docs/experiments/neural-max-stress/checkpoint.json \
  --output ../../.run/neural-max-repeat.json
```
