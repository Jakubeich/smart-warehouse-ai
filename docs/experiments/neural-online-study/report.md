# Jak průběžné učení ovlivnilo průjezd úzkými místy

Na 40 nových skladech s průjezdy širokými jednu buňku stoupla úspěšnost z **36/40 na 40/40**. Před učením se tři běhy zastavily po 30 krocích bez pokroku u průjezdu. Jeden další dosáhl limitu 1 600 kroků. Po učení všechny čtyři mapy doběhly. Celková doba byla ve společně dokončených dvojicích mírně delší.

## Měření

Výchozí model `nn-975367e33160` absolvoval **96 simulací** s automatickým učením z vlastních akcí, z toho 72 v mapách s jednobuněčnými průjezdy. Backend použil stejný postup jako živá aplikace. Po každých 64 krocích s dostupnými zkušenostmi a na konci běhu upravil váhy. Vzniklo **500 aktualizací ze 105 505 zkušeností**, model `nn-17a7071a6ab3`. Při sběru skončilo 87 běhů úspěšně, 8 selhalo a jeden dosáhl časového limitu v krocích. Celkem roboti dokončili 1 851 přeprav.

Po učení jsme obě verze vyhodnotili na stejných **60 nových mapách**, vždy s totožnou počáteční konfigurací. Mapy zahrnovaly 4, 6 nebo 8 robotů, 16–24 přeprav v obou směrech a tři typy uspořádání. Před sběrem se uložily testovací scénáře. Kontrola potvrdila odlišné geometrie překážek od 39 úvodních i 96 průběžných tréninkových map. Testovací jízdy používaly pevné váhy a nevstoupily do učení.

| Typ skladu | Map | Dokončeno před učením | Dokončeno po učení |
|---|---:|---:|---:|
| Průjezd široký jednu buňku | 40 | 36 | 40 |
| Průjezd široký dvě buňky | 10 | 10 | 10 |
| Otevřený sklad | 10 | 10 | 10 |
| Celkem | 60 | 56 | 60 |

Na úzkých mapách:

- Počet běhů s alespoň jedním čekáním dlouhým 10 kroků v kuse klesl z **13 na 9**.
- Ve 36 dvojicích, kde dokončily obě verze, klesl součet čekání robotů u průjezdů v průměru z **37,3 na 33,3 kroku na mapu**. Metrika počítá čekání jedoucích robotů v průjezdu a jeho bezprostředním okolí.
- Dokončení celé mapy v těchto dvojicích trvalo **283,7 → 287,8 kroku** v průměru, tedy o 1,4 % déle.

Ve všech **120 testovacích jízdách** bylo nula vykonaných kolizí. Výsledek ukazuje lepší spolehlivost v tomto vzorku. Dvojice, v nichž se výsledek dokončení změnil, jsou čtyři, a všechny ve prospěch nové verze. Tak malý počet neposkytuje jistotu stejného zlepšení na dalších mapách.

| Seed mapy | Před učením | Po učení |
|---|---|---|
| 1020001 | Bez pokroku po 7 z 16 přeprav | Hotovo za 239 kroků |
| 1020025 | Bez pokroku před dokončením první přepravy | Hotovo za 284 kroků |
| 1020026 | Limit 1 600 kroků, 15 z 20 přeprav | Hotovo za 231 kroků |
| 1020037 | Bez pokroku po 15 z 16 přeprav | Hotovo za 188 kroků |

## Data a reprodukce

[Plán a scénáře](plan.json) · [Tréninkové jízdy](training.json) · [Všechny páry](pairs.json) · [Souhrn](summary.json) · [Výchozí váhy](before-model.json) · [Checkpoint po učení](after-checkpoint.json)

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --directory apps/backend python \
  ../../scripts/study-online-neural-fleet.py --output ../../.run/neural-online-repeat
```

Skript používá izolovanou databázi a uloží váhy, scénáře a metriky do nového adresáře. Pro již existující váhy lze předat soubor checkpointu pomocí `--start-checkpoint`. Výše uvedené měření začíná u výchozích vah z projektu.
