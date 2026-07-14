# STW WoofMC v2.0.0

Externí makro recorder pro klávesnici a myš. Python + PyQt5.

## Struktura projektu

```
STW_WoofMC/
├── main.py              hlavní okno, UI, orchestrace všeho
├── macro_engine.py       nahrávání/přehrávání, MacroRecorder + MacroPlayer
├── input_backend.py       3 vstupní backendy (pynput / Windows Scan Code / PostMessage)
├── window_utils.py        výběr okna/procesu, PostMessage primitiva (Windows-only)
├── dialogs.py             Nastavení, editace události, hotkey capture
├── storage.py             JSON perzistence maker/playlistů/configu
├── theme.py               QSS téma + spacing tokeny
├── fx.py                  glow efekty, status orb, timeline widget
├── requirements.txt        runtime závislosti (PyQt5, pynput)
├── woofmc.spec             PyInstaller spec pro .exe build
├── build_exe.py            build skript (python build_exe.py)
├── STW_WoofMC.sln          Visual Studio solution
├── STW_WoofMC.pyproj        Visual Studio Python projekt (PTVS)
└── README.md               tenhle soubor
```

## Instalace

```
pip install -r requirements.txt
python main.py
```

## Otevření ve Visual Studiu

Vyžaduje workload **Python Development** (Visual Studio Installer → Upravit →
zaškrtnout Python Development). Bez něj VS soubor `.pyproj` neotevře.

1. Otevři `STW_WoofMC.sln`
2. V Solution Exploreru nastav svůj Python interpreter (pravé tlačítko na
   "Python Environments" → Add Environment, ukázat na venv s nainstalovaným
   `requirements.txt`)
3. F5 spustí `main.py` přímo v debuggeru

Poznámka: tohle je Python projekt otevřený ve VS přes PTVS, ne C++ port.
Kompletní přepis do C++ by znamenal jiný jazyk i jiné Qt bindings (Qt Widgets
C++ API místo PyQt5) — řádově jiná investice, prakticky nový projekt od nuly.

## Build .exe (Windows)

```
python build_exe.py
```

Musí běžet na Windows — PyInstaller nedělá cross-compile. Výstup:
`dist/STW_WoofMC/STW_WoofMC.exe`.

## Co je nové oproti v1

- Bezpečný stop přehrávání — všechny podržené klávesy/tlačítka myši se
  garantovaně uvolní i při chybě nebo přerušení (dřív mohly zůstat "zaseklé").
- Volitelný Windows Scan Code vstupní backend (`SendInput` + scan-code
  injekce) pro lepší kompatibilitu s hrami na DirectInput/RawInput, vedle
  původního univerzálního pynput backendu. Přepíná se v Nastavení.
- Pauza/resume přehrávání (výchozí hotkey F11).
- Ruční editace jednotlivých událostí (dvojklik na řádek), duplikace,
  vkládání čekání, přetahování řádků myší pro změnu pořadí (časy se
  přepočítají podle původních mezer mezi událostmi).
- Vyhledávání v seznamu makra, statistika počtu událostí a délky.
- Playlist — sekvenční přehrání víc maker za sebou, každé s vlastním počtem
  opakování a prodlevou mezi kroky.
- Editovatelné hotkeys (nahrávání/přehrávání/pauza) přímo v Nastavení,
  bez ruční editace JSON configu.
- Záloha a obnova celé knihovny maker + playlistů + configu do jednoho
  JSON souboru.
- Tray ikona mění barvu podle stavu (nahrávání/přehrávání/pauza/klid).
- Výběr cílového okna (Nastavení → Cílové okno) — hotkeys pro
  nahrávání/přehrávání/pauzu se spustí jen když je vybrané okno aktivní
  v popředí. Nevztahuje se na ovládání tlačítky přímo v aplikaci (kliknutím
  vždy přebereš fokus na WoofMC, takže restrikce by tam nedávala smysl).
  Volitelně lze zapnout automatické přepnutí na cílové okno těsně před
  spuštěním přehrávání. Funguje jen na Windows (`EnumWindows`/
  `SetForegroundWindow`), na jiných platformách je sekce v nastavení
  needitovatelná a restrikce se chová jako vypnutá.
- Vizuální upgrade v rámci PyQt5 — gradientová tlačítka, pulzující glow
  (`QGraphicsDropShadowEffect` + `QPropertyAnimation`) na nahrávání/
  přehrávání/pauze dokud jsou aktivní, plynulý barevný přechod stavové
  kontrolky (`QVariantAnimation` interpoluje `QColor`) místo tvrdého
  přepnutí, a timeline vizualizace makra nad tabulkou — tečky podle typu
  události plus pohybující se hlava přehrávání. Timeline je jen informativní,
  bez klikacího scrubování (zásah doprostřed přehrávání by mohl nechat
  klávesy podržené v nekonzistentním stavu).
- Oprava reálného bugu v nahrávání: držená klávesa (např. W při chůzi)
  už negeneruje desítky redundantních `key_down` událostí kvůli OS
  auto-repeatu — zaznamená se jen jeden skutečný stisk a jedno puštění.
- Oprava reálného bugu v editaci: po přetažení řádků myší se tabulka vždy
  znovu vykreslí přesně podle `current_events`, i kdyby Qt při vícenásobném
  výběru přesun položek zpackal — dřív mohla tabulka a datový model zůstat
  nesynchronizované a dvojklik pak upravil jiný event, než který byl vidět.
- Undo (Ctrl+Z nebo tlačítko "Zpět") pro editaci, mazání, duplikaci,
  vkládání čekání i přetažení řádků — 25 kroků historie na makro.
- **PostMessage backend (vstup na pozadí, bez fokusu)** — třetí volba
  vstupního backendu vedle pynput a Windows Scan Code. Posílá vstup přímo
  na konkrétní HWND cílového okna přes `PostMessage`, takže okno nemusí
  být aktivní ani v popředí. Funguje jen u klasických Win32 aplikací, které
  vstup zpracovávají přes zprávy okna — **naprostá většina her tuhle
  techniku úplně ignoruje**, protože čtou vstup přímo z hardwaru/DirectInputu.
  Tohle NENÍ obchvat anticheatu ani her obecně, je to samostatná technika
  pro jiný typ cíle (utility okna, klasické formulářové aplikace apod.).
- **Režim cílového okna "Stačí, že běží"** — v Nastavení lze u omezení
  hotkeys zvolit, jestli cílové okno musí být aktivní v popředí, nebo jestli
  stačí, že běží (i na pozadí/minimalizované). V kombinaci s PostMessage
  backendem tohle dává skutečnou "background" funkčnost — hotkey můžeš
  zmáčknout, zatímco děláš cokoliv jiného, a vstup doletí do cíle bez
  přepnutí okna. Samotné globální hotkeys (F9/F10/F11) fungují na pozadí
  vždy, bez ohledu na tohle nastavení — to je vlastnost `pynput.GlobalHotKeys`.
- Editace hotkeys teď podporuje kombinace s modifikátory (Ctrl/Alt/Shift/Win),
  ne jen jednu klávesu — např. `Ctrl+Alt+F9`.
- Klávesové zkratky v editoru: `Delete` smaže vybrané řádky, `Ctrl+D`
  duplikuje vybrané řádky (obě jen když má fokus tabulka), `Ctrl+S` uloží
  aktuální makro odkudkoliv v okně.
- Přehled v seznamu maker — každá položka ukazuje počet událostí, po výběru
  makra se pod statistikou zobrazí kdy bylo vytvořeno/upraveno a kolikrát
  spuštěno.
- Vizuální rework — tmavší paleta, "card" panely s jemným stínem pro
  hloubku, bevel hrany na tlačítkách (světlejší nahoře/tmavší dole = dojem
  vypouklého povrchu, při stisku se to otočí = "zamáčklé"), sjednocený
  spacing podle 4/8/12/16/24px škály.
- Neošetřené výjimky se logují do `~/.stw_woofmc/crash.log` a zobrazí
  se srozumitelná hláška místo tichého pádu.

## Hotkeys (výchozí)

- `F9` — start/stop nahrávání
- `F10` — start/stop přehrávání
- `F11` — pauza/pokračování přehrávání

Dají se změnit v Nastavení → klik do pole → stisk požadované klávesy.

## Známé limity

- Windows Scan Code backend počítá souřadnice myši vůči primárnímu
  monitoru (`SM_CXSCREEN`/`SM_CYSCREEN`). Víc monitorů s absolutním
  polohováním není podporováno.
- Hry s kernel-level anticheatem (EAC, BattlEye, Vanguard) mohou globální
  hooky a syntetický vstup blokovat nebo detekovat bez ohledu na zvolený
  backend — to není a nemůže být tento nástroj schopný obejít.
- Hotkeys podporují jen jednu klávesu (bez modifikátorových kombinací).
- Výběr cílového okna se kontroluje jen v okamžiku stisku hotkey, ne
  průběžně během přehrávání — pokud přepneš okno uprostřed přehrávání
  makra, makro doběhne do konce.
- PostMessage backend cílí na top-level okno zadané v Nastavení, ne na
  konkrétní child-control uvnitř něj — u aplikací s komplexním layoutem
  (více vnořených kontrolek) se nemusí trefit tam, kam čekáš.
- Node-based vizuální editor maker (větvení, propojování bloků) není
  součástí této verze — je to samostatná, řádově větší investice; pokud ho
  chceš, popiš přesný workflow, který má řešit, a naplánujeme ho zvlášť.
