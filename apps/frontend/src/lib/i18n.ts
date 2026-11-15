/** Czech presentation helpers. API keys, identifiers and persisted records stay unchanged. */
import { z } from "zod";
z.config(z.locales.cs());
export const messages = {
  en: {
    dashboard: "Dashboard",
    warehouses: "Warehouses",
    simulation: "Simulation",
    robots: "Robots",
    tasks: "Tasks",
    experiments: "Experiments",
    analytics: "Analytics",
    settings: "Settings",
  },
  cs: {
    dashboard: "Přehled",
    warehouses: "Sklady",
    simulation: "Simulace",
    robots: "Roboti",
    tasks: "Úkoly",
    experiments: "Experimenty",
    analytics: "Analýza",
    settings: "Nastavení",
  },
} as const;
export type Locale = keyof typeof messages;
export function t(
  key: keyof typeof messages.cs,
  locale: Locale = "cs",
): string {
  return messages[locale][key];
}
export const statusLabels: Record<string, string> = {
  READY: "Připraveno",
  RUNNING: "Běží",
  PAUSED: "Pozastaveno",
  COMPLETED: "Dokončeno",
  FAILED: "Selhalo",
  STOPPED: "Zastaveno",
  SUCCESS: "Úspěch",
  CANCELLED: "Zrušeno",
  INTERRUPTED: "Přerušeno",
  IDLE: "Volný",
  ASSIGNED: "Přiřazeno",
  MOVING_TO_PICKUP: "Jede pro náklad",
  MOVING_TO_DROPOFF: "Veze náklad",
  LOADING: "Nakládá",
  UNLOADING: "Vykládá",
  WAITING: "Čeká",
  CHARGING: "Nabíjí se",
  BLOCKED: "Zablokováno",
  ERROR: "Chyba",
  OFFLINE: "Vyřazen",
  PENDING: "Čeká na přiřazení",
  IN_PROGRESS: "Probíhá",
  TIMEOUT: "Časový limit",
  NO_PLAN: "Plán nenalezen",
  UNSOLVABLE: "Neřešitelné",
  CONFLICT: "Konflikt",
  TICK_LIMIT: "Limit kroků",
  WALL_LIMIT: "Limit skutečného času",
  CONNECTED: "Připojeno",
  CONNECTING: "Připojování",
  DISCONNECTED: "Odpojeno",
  PICKUP: "Nakládka",
  DROPOFF: "Vykládka",
  RETURN: "Vrací se",
  CHARGE: "Nabíjení",
};
export const layerLabels = {
  grid: "Mřížka",
  paths: "Trasy",
  ids: "ID robotů",
  reservations: "Rezervace",
  conflicts: "Konflikty",
  stations: "Stanice",
  heatmap: "Teplotní mapa",
} as const;
export const toolLabels: Record<string, string> = {
  SELECT: "Výběr",
  FLOOR: "Podlaha",
  WALL: "Stěna",
  SHELF: "Regál",
  PICKUP: "Nakládka",
  DROPOFF: "Vykládka",
  CHARGER: "Nabíjení",
  OBSTACLE: "Překážka",
  ROBOT: "Robot",
  ERASE: "Guma",
};
export const robotPropertyLabels = {
  capacity: "Nosnost (kg)",
  battery: "Aktuální energie",
  battery_capacity: "Kapacita baterie",
} as const;
const nouns = {
  robot: ["robot", "roboti", "robotů"],
  task: ["úkol", "úkoly", "úkolů"],
  tick: ["krok", "kroky", "kroků"],
  run: ["běh", "běhy", "běhů"],
  scenario: ["scénář", "scénáře", "scénářů"],
  event: ["událost", "události", "událostí"],
  cell: ["buňka", "buňky", "buněk"],
} as const;
const plurals = new Intl.PluralRules("cs-CZ");
export function counted(n: number, noun: keyof typeof nouns): string {
  const category = plurals.select(n);
  return `${new Intl.NumberFormat("cs-CZ").format(n)} ${nouns[noun][category === "one" ? 0 : category === "few" ? 1 : 2]}`;
}
export const formatDate = (date: string) =>
  new Intl.DateTimeFormat("cs-CZ", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Prague",
  }).format(new Date(date));
export const searchText = (value: string) =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("cs-CZ");
const demoNames: Record<string, string> = {
  "Small Warehouse": "Malý sklad",
  "Medium Warehouse": "Střední sklad",
  "Large Warehouse": "Velký sklad",
};
export function displayName(name: string): string {
  if (demoNames[name]) return demoNames[name];
  return name.replace(
    /^([A-F]) · (Static MAPF|Transport) comparison$/,
    (_, id: string, mode: string) =>
      `${id} · Porovnání: ${mode === "Static MAPF" ? "statický MAPF" : "přeprava"}`,
  );
}
const errorMessages: Record<string, string> = {
  "Database unavailable. Check PostgreSQL and migrations.":
    "Databáze není dostupná. Zkontrolujte PostgreSQL a databázové migrace.",
  "Active simulation not found. It may have ended at backend restart.":
    "Aktivní simulace nebyla nalezena. Mohla zaniknout při restartu serveru.",
  "Warehouse not found": "Sklad nebyl nalezen",
  "Scenario not found": "Scénář nebyl nalezen",
  "Experiment not found": "Experiment nebyl nalezen",
  "Run not found": "Běh nebyl nalezen",
  "Simulation not found": "Simulace nebyla nalezena",
  "Warehouse ID already exists": "Sklad s tímto ID již existuje",
  "Path and warehouse IDs differ": "ID skladu neodpovídá ID v požadavku",
  "Warehouse is referenced by a saved scenario": "Sklad používá uložený scénář",
  "Scenarios must contain initial robot configurations":
    "Scénář musí obsahovat počáteční nastavení robotů",
  "Scenarios must contain pending initial tasks":
    "Scénář musí obsahovat počáteční čekající úkoly",
  "Limit of 8 active sessions. Delete an old session first.":
    "Je dosažen limit osmi aktivních simulací. Nejprve ukončete některou starší simulaci.",
  "Provide a scenario or scenario_id": "Vyberte scénář nebo zadejte jeho ID",
  "Cell outside warehouse": "Buňka leží mimo sklad",
  "Duplicate cell coordinates": "Více buněk má stejné souřadnice",
  "Battery exceeds capacity": "Aktuální energie překračuje kapacitu baterie",
  "Entity IDs must be unique within a collection":
    "ID jednotlivých entit musí být jedinečná",
  "Robots cannot share a start cell": "Roboti nemohou začínat na stejné buňce",
  "Robots must have distinct home cells":
    "Každý robot musí mít vlastní domovskou buňku",
  "Robot start/home must be traversable":
    "Počáteční i domovská buňka robota musí být průchozí",
  "Task pickup must be a PICKUP station":
    "Místo nakládky musí být stanicí nakládky",
  "Task dropoff must be a DROPOFF station":
    "Místo vykládky musí být stanicí vykládky",
  "Task stations are disconnected":
    "Mezi stanicemi úkolu neexistuje průchozí cesta",
  "No robot can reach task pickup":
    "Žádný robot se nedostane ke stanici nakládky",
  "Transition changed fleet membership":
    "Při kroku se neočekávaně změnil počet robotů",
  "Vertex collision rejected": "Pohyb byl odmítnut: kolize na stejné buňce",
  "Invalid robot movement rejected": "Neplatný pohyb robota byl odmítnut",
  "Edge-swap collision rejected":
    "Pohyb byl odmítnut: kolize při vzájemné výměně buněk",
  "Invalid battery level": "Neplatná úroveň baterie",
  "Invalid completed task history": "Neplatná historie dokončeného úkolu",
  "Run saved after database recovery": "Po obnovení databáze byl běh uložen",
  "Run could not be saved. Export the snapshot; database save will retry.":
    "Běh se nepodařilo uložit. Exportujte snímek stavu; uložení do databáze se zopakuje.",
  "Scenario reset to its initial state":
    "Scénář byl obnoven do počátečního stavu",
  "Reset a finished run before starting it again":
    "Před opětovným spuštěním obnovte dokončený běh",
  "Simulation running": "Simulace byla spuštěna",
  "Simulation paused": "Simulace byla pozastavena",
  "Pause before single stepping": "Před jednotlivým krokem simulaci pozastavte",
  "Reset a finished simulation before stepping":
    "Před krokováním obnovte dokončenou simulaci",
  "Simulation stopped by user": "Simulace byla zastavena uživatelem",
  "Unknown simulation action": "Neznámý příkaz simulace",
  "Map has too few traversable start cells":
    "Mapa nemá dostatek průchozích počátečních buněk",
  "Transport benchmarks require pickup and dropoff stations":
    "Experimenty s přepravou vyžadují stanice nakládky a vykládky",
  "Static MAPF does not compare task schedulers":
    "Statický MAPF neporovnává přiřazování úkolů",
  "Duplicate fleet sizes": "Počty robotů se nesmějí opakovat",
  "Benchmark fleets must contain 1–16 robots":
    "Experiment musí používat 1–16 robotů",
  "Dynamic obstacles and scheduling require transport mode":
    "Dynamické překážky a přiřazování úkolů vyžadují režim přepravy",
  "Duplicate algorithms or schedulers":
    "Algoritmy a způsoby přiřazování se nesmějí opakovat",
  "Maximum 120 runs per experiment":
    "Jeden experiment může obsahovat nejvýše 120 běhů",
  "At most two experiments can run concurrently":
    "Současně mohou běžet nejvýše dva experimenty",
  "Starts and goals must have the same nonempty robot IDs":
    "Počátky a cíle musí mít stejná neprázdná ID robotů",
  "Initial and goal positions must each be unique (stay-at-goal)":
    "Počáteční a cílové pozice musí být jedinečné; robot zůstává v cíli",
  "All endpoints must be traversable":
    "Všechny počátky a cíle musí být průchozí",
  "Disconnected endpoint": "Počátek a cíl nejsou propojené",
  "Independent A* routes conflict": "Nezávislé trasy A* jsou v konfliktu",
  "Priority order or horizon prevents a plan":
    "Pořadí priorit nebo plánovací horizont neumožňuje nalézt plán",
  "Planning time limit exhausted": "Byl vyčerpán časový limit plánování",
  "CBS resource limit exhausted; feasibility is unknown":
    "CBS vyčerpal limit zdrojů; řešitelnost není známá",
  "CBS low-level time limit exhausted; feasibility is unknown":
    "Hledání dílčí cesty CBS vyčerpalo časový limit; řešitelnost není známá",
  "Exhausted conflict tree": "Strom konfliktů byl prohledán bez řešení",
  "A scenario must contain initial idle robot configurations":
    "Scénář musí obsahovat roboty v počátečním klidovém stavu",
  "A scenario must contain initial pending tasks created at tick zero":
    "Scénář musí obsahovat počáteční čekající úkoly vytvořené v kroku nula",
  "All transport tasks completed.": "Všechny přepravní úkoly byly dokončeny.",
  "Simulation step limit reached.": "Simulace dosáhla limitu kroků.",
  "Training attempt reached its tick limit.": "Pokus dosáhl limitu kroků.",
  "Training attempt rejected because more robots ran out of energy.":
    "Pokus skončil předčasně, protože se vybilo více robotů než při nejlepším běhu.",
  "Training progress could not be saved. Try again.":
    "Zkušenosti se zatím nepodařilo uložit. Zkuste to znovu.",
  "No progress for 30 ticks: check capacity, energy, station admission or reachability":
    "Po dobu 30 kroků nedošlo k pokroku. Zkontrolujte nosnost, energii, obsazení a dostupnost stanic.",
  "Most available robots are out of energy.": "Většina dostupných robotů se vybila.",
  "The fleet is repeating the same state without completing a delivery.":
    "Flotila se vrací do stejného stavu a nedokončuje přepravy.",
  "Task limit reached or duplicate ID":
    "Byl dosažen limit úkolů nebo se opakuje jejich ID",
  "New tasks must be pending and unassigned":
    "Nové úkoly musí čekat na přiřazení",
  "Dynamic obstacles disconnect stations":
    "Dynamické překážky přerušily cestu mezi stanicemi",
  "No dynamic obstacle at this cell": "Na této buňce není dynamická překážka",
  "Obstacles require an empty floor cell, away from robot homes":
    "Překážku lze umístit jen na volnou podlahu mimo domovské buňky robotů",
  "Unknown robot": "Robot nebyl nalezen",
  "Only an idle robot can change availability":
    "Dostupnost lze změnit pouze u nečinného robota",
  "Failed to fetch":
    "Server není dostupný. Zkontrolujte připojení a zkuste to znovu.",
  "Load failed": "Načítání selhalo. Zkontrolujte spojení se serverem.",
  "NetworkError when attempting to fetch resource.":
    "Spojení se serverem se nezdařilo.",
  "Backend restarted during experiment":
    "Server se během experimentu restartoval",
};
const plannerNames: Record<string, string> = {
  astar: "A*",
  prioritized: "Prioritizované plánování",
  cbs: "CBS",
  adaptive: "Adaptivní plánování",
};
const patterns: {
  pattern: RegExp;
  translate: (m: RegExpMatchArray) => string;
}[] = [
  {
    pattern: /^Scenario initialized\. (\d+) robots ready\.$/,
    translate: (m) => `Scénář je připraven. Počet robotů: ${m[1]}.`,
  },
  {
    pattern: /^(.+) assigned to (.+)$/,
    translate: (m) => `Úkol ${m[1]} byl přiřazen robotovi ${m[2]}`,
  },
  {
    pattern: /^(.+) delivered by (.+)$/,
    translate: (m) => `Úkol ${m[1]} dokončil robot ${m[2]}`,
  },
  {
    pattern: /^(.+) added to queue$/,
    translate: (m) => `Úkol ${m[1]} byl přidán do fronty`,
  },
  {
    pattern: /^Global plan: (\w+), cost (.+)\.$/,
    translate: (m) =>
      `Globální plán: ${plannerNames[m[1]] ?? m[1]}, cena ${m[2]}.`,
  },
  {
    pattern: /^Cell (.+) changed; global replanning required$/,
    translate: (m) =>
      `Buňka ${m[1]} byla změněna. Je nutné globální přeplánování.`,
  },
  {
    pattern: /^(.+) (available|offline)$/,
    translate: (m) =>
      `Robot ${m[1]} je ${m[2] === "available" ? "dostupný" : "vyřazený"}`,
  },
  {
    pattern: /^(.+): insufficient energy; transition rejected$/,
    translate: (m) => `${m[1]}: nedostatek energie; pohyb byl odmítnut`,
  },
  {
    pattern: /^(astar|prioritized|cbs|adaptive): (\w+)\. (.*)$/,
    translate: (m) =>
      `${plannerNames[m[1]]}: ${statusLabels[m[2]] ?? m[2]}. ${translateMessage(m[3])}`,
  },
  {
    pattern: /^Invalid robot transition (\w+) → (\w+)$/,
    translate: (m) =>
      `Nepovolená změna stavu robota: ${statusLabels[m[1]] ?? m[1]} → ${statusLabels[m[2]] ?? m[2]}`,
  },
  {
    pattern: /^Dynamic schedule could not be applied: (.+)$/,
    translate: (m) =>
      `Dynamickou změnu se nepodařilo provést: ${translateMessage(m[1])}`,
  },
  {
    pattern: /^Simulation error: (\w+): (.+)$/,
    translate: (m) => `Chyba simulace (${m[1]}): ${translateMessage(m[2])}`,
  },
  {
    pattern: /^(?:ValueError|InvariantError): (.+)$/,
    translate: (m) => translateMessage(m[1]),
  },
];
export function translateMessage(message: string): string {
  if (errorMessages[message]) return errorMessages[message];
  for (const { pattern, translate } of patterns) {
    const match = message.match(pattern);
    if (match) return translate(match);
  }
  // Pydantic currently sends a textual validation envelope; extract known domain guidance.
  if (
    message.includes("Value error,") ||
    message.includes("validation error") ||
    (message.includes("'msg':") && message.includes("'type':"))
  ) {
    const known = Object.keys(errorMessages).find((key) =>
      message.includes(key),
    );
    if (known) return errorMessages[known];
    return "Zadané údaje nejsou platné. Zkontrolujte povinná pole, rozsahy hodnot a strukturu scénáře.";
  }
  return message;
}
export function errorText(error: unknown): string {
  if (error instanceof z.ZodError)
    return error.issues.map((issue) => issue.message).join(" · ");
  if (error instanceof SyntaxError)
    return "Soubor neobsahuje platný JSON. Zkontrolujte jeho formát.";
  return translateMessage(
    error instanceof Error ? error.message : String(error),
  );
}

export function inputValidationMessage(input: HTMLInputElement): string {
  const validity = input.validity;
  if (validity.valueMissing) return "Vyplňte toto pole.";
  if (validity.badInput) return "Zadejte platné číslo.";
  if (validity.rangeUnderflow)
    return `Zadejte hodnotu alespoň ${Number(input.min).toLocaleString("cs-CZ")}.`;
  if (validity.rangeOverflow)
    return `Zadejte hodnotu nejvýše ${Number(input.max).toLocaleString("cs-CZ")}.`;
  if (validity.stepMismatch) return "Zadejte hodnotu v povoleném kroku.";
  if (validity.patternMismatch) return "Zadejte hodnotu v požadovaném formátu.";
  if (validity.tooLong) return "Zkraťte zadaný text.";
  if (validity.tooShort) return "Zadaný text je příliš krátký.";
  if (validity.typeMismatch) return "Zadejte platnou hodnotu.";
  return "Zkontrolujte zadanou hodnotu.";
}
