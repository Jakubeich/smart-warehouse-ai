# Odměny za uvolnění úzkého průjezdu

## Proč se některé jízdy po předchozím učení zhoršily

Přehrání jízd s pevnými váhami odhalilo dva různé problémy. Na mapách 1130019 a 1130042 tlačily dvojice robotů přímo proti sobě. Ve všech posledních 30 krocích si oba v dvojici navrhli vyměnit místa v jednobuněčném průjezdu. Simulátor návrhy odmítl a síť hodnotila čekání výš než ústup. Oba roboti tedy opakovali stejná rozhodnutí. Na mapě 1130019 se blokoval robot jedoucí pro náklad a robot mířící zpět. Na mapě 1130042 se blokoval robot s nákladem a robot mířící zpět.

Na mapě 1130016 čekali dva roboti s nákladem u průjezdu, zatímco opakované návraty a nabíjení udržovaly zbytek flotily v činnosti. Po 1 600 krocích dokončila síť 16 z 20 úkolů. Navrhla 261 akcí nabíjení a 260 parkování. Aktivní model na téže mapě dokončil všech 20 úkolů za 408 kroků se 7 akcemi nabíjení a 3 parkování. Metrika globálních 30 kroků bez pohybu, obsluhy či nabíjení tento typ čekání nezachytí. Proto dál měříme dlouhá čekání jednotlivých robotů a limit běhu.

Předchozí úprava měnila odměny hlavně za práci a nabíjení. Úspěšnou, ale pomalejší přepravu mohla označit zápornou odměnou. Zpětnou vazbu k práci a nabíjení přitom při aktualizaci vážila pětinásobně. Pohybová odměna sledovala hlavně vzdálenost vlastního robota od cíle. Ústup od něj tak mohl vyjít záporně, i když uvolnil cestu druhému. Přehrání ukazuje mechanismus blokování. Samostatný vliv každé z těchto změn odměny jsme v předchozím pokusu neměřili. [Počty akcí a konkrétní protisměrné návrhy](diagnosis.json)

## Změny odměny při tréninku

Síť dostává vygenerované sklady s jedním nebo dvěma jednobuněčnými průjezdy. Každý krok navrhne sama a simulátor jej prověří stejně jako při živé jízdě. Odměna dorazí až po pozorované akci nebo jejím výsledku.

- Doplňkovou odměnu získá robot za skutečný průjezd z jedné strany bariéry na druhou.
- Když někdo projede, trénink kladně ohodnotí i nedávný ústup od cíle nebo čekání jiného robota u stejného průjezdu. Sleduje okno osmi kroků a použije nejvýše jednu zkušenost na robota a událost. Jde o připsání zásluhy podle pozorované časové souvislosti.
- Když běh skončí bez pokroku, trénink penalizuje poslední takové akce čekajících robotů u průjezdu. Dosavadní zpětná vazba k odmítnutým kolizním návrhům se dál používá.
- Druhá větev navíc dává větší odměnu rychlejším z pozorovaných úspěšných přeprav a váže odměnu za nabíjení na chybějící energii. Úspěšné přepravy mají kladnou odměnu i při zpoždění.

Obě větve vycházejí z aktivní verze `nn-17a7071a6ab3` a každá trénuje na stejných 64 mapách. Po 8, 16, 32 a 64 jízdách se uložené váhy porovnávají na 32 validačních mapách. Při výběru mají přednost dokončené jízdy, nižší počet zastavení a méně map s dlouhým čekáním. Čas se počítá na společně dokončených dvojicích. Testovací sada obsahuje dalších 64 scénářů. Pro každou z flotil se 4, 6, 8 a 12 roboty zahrnuje 16 map. Všechny mají obousměrné přepravy. Geometrie jsou odlišné od dříve použitých map, nového tréninku i validace.

## Test na 64 nových mapách

Na validaci vyšla nejlépe verze `nn-6fbbad0b2260` po 16 jízdách s odměnou za průjezd a ústupek. Síť přidala 72 aktualizací z 14 580 zkušeností. Trénink této verze zaznamenal 508 odměn za průjezd a 170 odměn za uvolnění cesty dalšímu robotovi. Na validaci dokončila 31 z 32 map oproti 29 z 32. Ve 29 společně dokončených jízdách snížila čas z 273,1 na 264,6 kroku.

| Metrika | Aktivní model | Model po úpravě odměn |
| --- | ---: | ---: |
| Dokončené mapy | 59/64 | 62/64 |
| Zastavení bez pokroku u průjezdu | 4 | 1 |
| Mapy s čekáním u průjezdu alespoň 10 kroků | 18 | 12 |
| Běhy na limitu 1 600 kroků | 1 | 1 |
| Průměrný čas dokončení na stejných 59 mapách | 274,4 | 279,6 |
| Průměrný součet čekání robotů u průjezdu na stejných 59 mapách | 40,1 | 31,5 |
| Provedené kolize | 0 | 0 |

Upravený model dokončil všechny mapy, které zvládl aktivní model, a tři navíc. Na 59 společně dokončených mapách zrychlil 18 jízd, 5 mělo stejný čas a 36 zpomalilo. Celkový čas vzrostl v průměru o 5,3 kroku, tedy o 1,9 %. Součet čekání u průjezdu v této skupině klesl o 21 %. Kroky jsou jednotky času simulátoru. Při testu se váhy obou modelů po celou dobu používají bez aktualizací. [Výsledky po mapách](pairs.json) · [Souhrn testu](summary.json) · [Výběr na validaci](validation-summary.json)

## Menší posuny vah

Po prvním testu jsme vyzkoušeli 10 %, 25 %, 50 % a 75 % rozdílu mezi váhami aktivního a upraveného modelu. Jako validační sada posloužilo všech 96 map z validace a testu prvního pokusu. Aktivní model dokončil 88 map, zastavil se v zóně průjezdu na 6 a měl dlouhé čekání na 27. U všech čtyř variant vyšel průměrný čas na společně dokončených mapách delší. Nejmenší rozdíl byl +0,35 kroku u čtvrtinového posunu, který dokončil o dvě mapy méně. Tyto čtyři varianty se na připravené oddělené sadě netestovaly. [Srovnání na 96 mapách](smaller-update/validation-summary.json)

## Cílená odměna za ústup

V dalším tréninku jsme vynechali kladnou odměnu za samotné čekání. Odměna za skutečný průjezd zůstala a zásluhu za uvolnění cesty mohl získat jen robot, který předtím u stejného průjezdu ustoupil od cíle. Pokud oba roboti opakovaně navrhli výměnu míst a oba skutečně zůstali stát, získaly tyto návrhy dodatečnou zápornou odměnu. Výpočet skóre při jízdě a kontrola pohybu jsou shodné s prvním pokusem.

Síť vyšla z aktivního modelu a trénovala na dalších 32 mapách. Úprava zaznamenala 2 596 dodatečných postihů za opakované návrhy výměny míst, včetně opakovaných zkušeností jedné dvojice. Stav po 4, 8, 16 a 32 jízdách se prověřil na stejných 96 validačních mapách jako menší posuny vah. Pro samostatný test je vyhrazeno dalších 64 map z původně nevyužité testovací sady menších posunů. [Mapy a pravidlo výběru](focused/plan.json) · [Výsledky tréninku](focused/training.json)

Verze po 8 jízdách zkrátila čas na 84 společně dokončených mapách o 0,7 kroku. Počet zastavení u průjezdů vzrostl ze 6 na 7. Verze po 32 jízdách dokončila 92 map místo 88, měla 3 zastavení místo 6 a dlouhé čekání na 19 mapách místo 27. Ve společně dokončených jízdách ale potřebovala o 5,1 kroku více. Žádná ze čtyř verzí nesplnila rychlost a průjezdnost současně, takže vyhrazená sada zůstala nepoužitá. [Výsledky po jednotlivých verzích](focused/validation-summary.json)

## Nasazení a reprodukce

Živá aplikace dál používá `nn-17a7071a6ab3` a dosavadní odměny při automatickém učení. Nové odměny byly použity v oddělených tréninkových simulacích. V kontrolovaném testu snížily riziko zastavení, ale nedoložily zároveň rychlejší dokončení. Přínos se vztahuje k testované rodině procedurálních map se zúženou bariérou.

Opakování prvního pokusu reprodukovalo všech 24 výstupních souborů JSON včetně vah a výsledků po mapách. Geometrie map a metriky z párových výsledků byly zkontrolovány i samostatně.

Příkazy spusťte z kořene projektu. Očekávají existující archiv výchozího modelu a původních map. Každý zapisuje do nového výstupního adresáře. [Výchozí váhy](before-checkpoint.json) · [Vybrané váhy](after-checkpoint.json) · [Otisky souborů](source-hashes.json)

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --directory apps/backend python \
  ../../scripts/study-neural-yield.py --output ../../.run/neural-yield-repeat \
  --start-checkpoint ../../docs/experiments/neural-yield-study/before-checkpoint.json

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --directory apps/backend python \
  ../../scripts/study-neural-yield-blend.py --output ../../.run/neural-yield-blend-repeat

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --directory apps/backend python \
  ../../scripts/study-neural-yield-focused.py --output ../../.run/neural-yield-focused-repeat
```
