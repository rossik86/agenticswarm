# Agentic Swarm Town: biuro AI, w ktorym widac jak agenci naprawde pracuja

Wiekszosc systemow multi-agentowych dziala jak czarna skrzynka: wysylasz prompt, czekasz i na koncu dostajesz wynik. Agentic Swarm Town robi cos odwrotnego. Pokazuje caly przebieg pracy agentow w formie interaktywnego biura: kto przejal zadanie, ktory pokoj aktualnie pracuje, gdzie pojawil sie blad, jakie artefakty powstaly, ile tokenow kosztowal dany etap i z ktorego checkpointu mozna wznowic proces.

Zbudowalismy aplikacje, ktora laczy backend CLI do wykonywania zadan agentowych z webowym dashboardem observability. Celem nie bylo tylko "odpalic kilku agentow", ale stworzyc srodowisko, w ktorym da sie kontrolowac, analizowac i usprawniac prace calego runu.

## Po co powstala aplikacja?

Przy pracy z agentami szybko pojawiaja sie konkretne problemy:

- trudno sprawdzic, ktory agent podjal dana decyzje,
- trudno odroznic realny output od posrednich notatek,
- trudno zrozumiec, gdzie run utknal,
- trudno wznowic prace od konkretnego checkpointu,
- trudno mierzyc koszt pracy per agent, pokoj i caly run,
- trudno zarzadzac promptami, skillami, MCP i modelami bez grzebania w plikach.

Agentic Swarm Town odpowiada na te problemy przez polaczenie orkiestracji agentow, artefaktow markdown, checkpointow, token usage i GUI pokazujacego prace systemu w czasie rzeczywistym.

## Jak dziala swarm?

Run zaczyna sie od agenta Main, ktory przyjmuje zadanie od uzytkownika i przekazuje je dalej do Supervisora. Supervisor rozumie cel, planuje przebieg pracy i uruchamia kolejne pokoje:

- Analyst Council analizuje problem, szuka ryzyk, doprecyzowuje wymagania i przygotowuje specyfikacje.
- Research Council zbiera informacje, jezeli zadanie wymaga wiedzy zewnetrznej lub weryfikacji.
- Builder Bay realizuje zadanie: plan, kod, dokumentacje albo inny artefakt wynikowy.
- Review Council sprawdza jakosc, ryzyka, bezpieczenstwo i zgodnosc z celem.
- Learning Lab analizuje caly run i proponuje usprawnienia dla agentow, promptow i flow.

Kazda rada agentow ma role wewnetrzne: pozytywna, negatywna i neutralna. Pozytywny agent szuka mocnych stron i mozliwosci, negatywny grilluje zalozenia i szuka dziur, a neutralny rozsadza dyskusje i przekazuje uzgodniony wynik dalej. Z pokoju nie wychodzi przypadkowy tekst, tylko uzgodniony artefakt.

## Co widac w dashboardzie?

GUI jest zrobione jako pixel-artowe biuro agentow. Pokoje sa ulozone wokol Main CO, czyli centrum dowodzenia. Kazdy pokoj i kazdy agent jest klikalny. Po kliknieciu mozna zobaczyc:

- status agenta lub pokoju,
- stance i role,
- prompt, instrukcje, skille i MCP,
- wejscie i wyjscie w ramach aktualnego runu,
- artefakty markdown,
- checkpointy,
- historie zdarzen,
- token usage z podzialem na input i output.

Flow runu jest pokazany jako warstwa polaczen miedzy pokojami. Kolejne przejscia sa kolorowane, a panel progresu pozwala przechodzic od checkpointa do checkpointa i ogladac, jak zmienial sie stan wykonania.

## Observability zamiast zgadywania

Najwazniejsza wartosc tej aplikacji to observability. Nie trzeba juz zgadywac, czy problem powstal w analizie, researchu, budowaniu czy review. Kazdy etap zostawia slad:

- eventy,
- checkpointy,
- artefakty,
- token usage,
- statusy agentow,
- statusy pokoi,
- wejscia i wyjscia.

Dzieki temu da sie wrocic do konkretnego miejsca, wznowic run, przeanalizowac blad albo poprawic konfiguracje wybranego agenta.

## Konfiguracja bez recznego grzebania

Aplikacja ma panel konfiguracji po lewej stronie. Mozna w nim zarzadzac agentami, skillami, MCP, providerem i modelem. Jest tez onboarding dla nowych uzytkownikow, ktory pozwala ustawic providera i model dla wszystkich agentow jednoczesnie.

Aktualnie aplikacja wspiera podejscie adapterowe dla providerow, m.in. Codex CLI, Agents SDK, Copilot i OpenHands. Dzieki temu backend moze rozwijac obsluge roznych silnikow agentowych bez przepisywania calego dashboardu.

## Learning Lab, czyli agent od poprawy systemu

Learning Lab nie jest tylko "komentatorem". Analizuje przebieg runu i przygotowuje propozycje usprawnien. Zmiany nie sa stosowane automatycznie. Uzytkownik musi je zatwierdzic przyciskiem, dzieki czemu system moze sie poprawiac, ale nie traci kontroli nad konfiguracja.

To wazne, bo w systemach agentowych automatyczne modyfikowanie promptow i instrukcji bez zatwierdzenia szybko robi sie ryzykowne. Tutaj learning jest kontrolowany: agent proponuje, czlowiek decyduje.

## Instrukcja po ekranach

### 1. Widok glowny town

Na glownym ekranie widac cale biuro agentow: Main CO w centrum, pokoje wokol niego, aktualne statusy i flow wykonania runu.

![Widok glowny town](gui-guide/01-town-overview.png)

### 2. Lista runow

Panel runow pozwala przelaczac sie pomiedzy wykonaniami, wyszukiwac runy po nazwie i dacie oraz sprawdzac status ostatnich zadan.

![Lista runow](gui-guide/02-run-picker.png)

### 3. Panel szczegolow

Po kliknieciu agenta albo pokoju wysuwa sie prawy panel. W nim znajduja sie dane tylko dla aktualnie wybranego runu: status, artefakty, checkpointy, historia i token usage.

![Panel szczegolow](gui-guide/03-inspector-panel.png)

### 4. Konfiguracja i onboarding

Lewy panel sluzy do konfiguracji agentow, skillow, MCP i providerow. Onboarding pozwala szybko ustawic model i providera dla wszystkich agentow.

![Konfiguracja i onboarding](gui-guide/04-settings-onboarding.png)

### 5. Sam town bez paneli

Po zwinieciu paneli bocznych zostaje czysty widok miasta agentow. To najlepszy ekran do obserwowania przebiegu runu w czasie rzeczywistym.

![Town bez paneli](gui-guide/05-town-only-collapsed-panels.png)

## Co dalej?

To dopiero fundament. Najciekawsze kierunki rozwoju to:

- dokladniejsze replay runow krok po kroku,
- porownywanie runow miedzy soba,
- rekomendacje optymalizacji kosztu tokenow,
- wersjonowanie promptow i skillow,
- integracja z zewnetrznymi narzedziami observability,
- tryb zespolowy do pracy kilku osob nad tym samym swarmem.

Agentic Swarm Town pokazuje, ze multi-agentowe systemy nie musza byc czarna skrzynka. Moga byc czytelne, kontrolowalne i gotowe do realnej pracy inzynierskiej.
