class GeneratorGrafiku:
    """
    Algorytm "dokańczający" grafik.
    Szanuje wszystkie wpisane już zmiany (D, N, M, 4, UUW, L4, X),
    uwzględnia dozwolone dni pracy pracowników, ich dostępność,
    ciągłość dni przepracowanych oraz eliminuje 1-dniowe wolne.
    """

    def __init__(self, obj_miesiac, pracownicy, norma_miesiaca: float = 160.0):
        self.miesiac = obj_miesiac
        self.pracownicy = pracownicy
        self.norma_miesiaca = norma_miesiaca

    def _oblicz_godziny_zmiany(self, status: str, pracownik=None) -> float:
        if status in ["D", "N"]:
            return 12.0
        elif status == "M":
            return 8.0
        elif status == "4":
            return 4.0
        return 0.0


    def _oblicz_ciag_pracy(self, p_id: int, do_dnia_idx: int) -> int:
        """Zlicza, ile dni z rzędu (bezpośrednio wstecz od do_dnia_idx) pracownik przepracował."""
        ciag = 0
        for i in range(do_dnia_idx - 1, -1, -1):
            zmiana = self.miesiac.dni[i].pobierz_zmiane(p_id, domyslna="P")
            if zmiana in ["D", "N", "M", "4"]:
                ciag += 1
            else:
                break
        return ciag

    def _czy_tworzy_jednodniowe_wolne(self, p_id: int, biezacy_idx: int) -> bool:
        """
        Sprawdza, czy brak obsady dzisiaj utworzy 1-dniową "dziurę" wolnego
        (tj. wczoraj pracował, a jutro z powodu ograniczeń musiałby pracować).
        """
        if biezacy_idx == 0 or biezacy_idx >= len(self.miesiac.dni) - 1:
            return False

        poprzedni = self.miesiac.dni[biezacy_idx - 1].pobierz_zmiane(p_id, domyslna="P")
        nastepny_dzien = self.miesiac.dni[biezacy_idx + 1]
        pracownik = next(p for p in self.pracownicy if p.db_id == p_id)

        wczoraj_pracowal = poprzedni in ["D", "N", "M", "4"]
        jutro_musi_pracowac = not pracownik.moze_pracowac_w_dzien(nastepny_dzien.data)

        return wczoraj_pracowal and jutro_musi_pracowac

    def _oblicz_presje(self, pracownik, od_dnia_idx: int, wyrobione_godziny: float) -> float:
        """
        Wyznacza wskaźnik presji czasowej (0.0 - 1.0+).
        Im WYŻSZA wartość (bliższa lub większa od 1.0), tym BARDZIEJ pracownik potrzebuje
        przydziału pracy DZISIAJ, bo ma mało dostępnych dni w stosunku do braku godzin.

        Aby zachować sortowanie ROSNĄCE w _sortuj_pracownikow, zwracamy wartość UJEMNĄ
        (im większa presja, tym mniejsza/bardziej ujemna liczba -> wyższy priorytet).
        """
        # 1. Ile godzin brakuje pracownikowi do jego indywidualnej normy etatu
        norma_pracownika = pracownik.get_norma_miesiaca(self.norma_miesiaca)
        brakuje_godzin = max(0.0, norma_pracownika - wyrobione_godziny)

        # Przeliczamy brakujące godziny na orientacyjną liczbę potrzebnych dni (zakładając dni 12h)
        potrzebne_dni = brakuje_godzin / 12.0

        # 2. Liczymy, ile fizycznie dni pracownik MOŻE jeszcze przepracować od dziś do końca miesiąca
        dostepne_dni = sum(
            1 for dzien in self.miesiac.dni[od_dnia_idx:]
            if pracownik.moze_pracowac_w_dzien(dzien.data)
        )

        # Brak dostępnych dni lub norma wyrobiona - brak presji
        if dostepne_dni == 0 or potrzebne_dni <= 0:
            return 0.0

        # 3. Wskaźnik wykorzystania dostępności (np. potrzebuje 4 dni, ma 4 dni = 1.0 -> krytyczny brak czasu)
        presja = potrzebne_dni / dostepne_dni

        # Zwracamy wartość ujemną, aby w sortowaniu rosnącym najpierw trafiały osoby z największą presją
        return -presja

    def _sortuj_pracownikow(self, godziny_pracownikow: dict, biezacy_dzien_idx: int) -> list:
        """
        Sortowanie wielokryterialne:
        1. Unikanie pojedynczych dni wolnych (priorytet pracy, jeśli grozi 1-dniowe wolne)
        2. Najmniejszy ciąg dni przepracowanych z rzędu (osoby z długą serią trafiają na koniec kolejki do pracy)
        3. Liczba pozostałych dostępnych dni w miesiącu w zależności od godzin do wyrobienia (im mniej, tym wyższy priorytet do pracy)
        4. Wskaźnik niedoboru godzin (im mniejszy procent normy, tym wyższy priorytet do pracy)
        """
        return sorted(
            self.pracownicy,
            key=lambda p: (
                0 if self._czy_tworzy_jednodniowe_wolne(p.db_id, biezacy_dzien_idx) else 1,
                self._oblicz_ciag_pracy(p.db_id, biezacy_dzien_idx),
                self._oblicz_presje(p, biezacy_dzien_idx, godziny_pracownikow[p.db_id]),
                godziny_pracownikow[p.db_id] / p.get_norma_miesiaca(self.norma_miesiaca)
            )
        )

    def generuj(self) -> bool:
        godziny_pracownikow = {p.db_id: 0.0 for p in self.pracownicy}

        # 1. Zliczamy godziny z wpisów ręcznych
        for dzien in self.miesiac.dni:
            for p in self.pracownicy:
                stary_status = dzien.pobierz_zmiane(p.db_id, domyslna="P")
                godziny_pracownikow[p.db_id] += self._oblicz_godziny_zmiany(stary_status, p)

        # 2. Pętla uzupełniająca brakujące obsady dzień po dniu
        for idx, dzien in enumerate(self.miesiac.dni):
            poprzedni_dzien = self.miesiac.dni[idx - 1] if idx > 0 else None

            suma_godzin_dnia = sum(
                self._oblicz_godziny_zmiany(dzien.pobierz_zmiane(p.db_id), p)
                for p in self.pracownicy
            )

            oblozenie_d = any(dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy)
            oblozenie_n = any(dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy)

            # --- Krok A: Obsada zmiany Dziennej 'D' ---
            if not oblozenie_d and suma_godzin_dnia < 24.0:
                dostepni_pracownicy = self._sortuj_pracownikow(godziny_pracownikow, idx)
                for p in dostepni_pracownicy:
                    if dzien.pobierz_zmiane(p.db_id) != "P":
                        continue
                    if not p.moze_pracowac_w_dzien(dzien.data):
                        continue

                    if self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien):
                        dzien.ustaw_zmiane(p.db_id, "D")
                        godziny_pracownikow[p.db_id] += 12.0
                        suma_godzin_dnia += 12.0
                        oblozenie_d = True
                        break

            # --- Krok B: Obsada zmiany Nocnej 'N' ---
            if not oblozenie_n and suma_godzin_dnia < 24.0:
                dostepni_pracownicy = self._sortuj_pracownikow(godziny_pracownikow, idx)
                for p in dostepni_pracownicy:
                    if dzien.pobierz_zmiane(p.db_id) != "P":
                        continue
                    if not p.moze_pracowac_w_dzien(dzien.data):
                        continue

                    if self._czy_moze_miec_noc(p.db_id, dzien, poprzedni_dzien):
                        dzien.ustaw_zmiane(p.db_id, "N")
                        godziny_pracownikow[p.db_id] += 12.0
                        suma_godzin_dnia += 12.0
                        oblozenie_n = True
                        break

            # --- Krok C: Uzupełnianie brakujących godzin (M / 4) ---
            if suma_godzin_dnia < 24.0:
                dostepni_pracownicy = self._sortuj_pracownikow(godziny_pracownikow, idx)
                for p in dostepni_pracownicy:
                    if suma_godzin_dnia >= 24.0:
                        break

                    if dzien.pobierz_zmiane(p.db_id) != "P":
                        continue
                    if not p.moze_pracowac_w_dzien(dzien.data):
                        continue

                    cel_godzin = p.get_norma_miesiaca(self.norma_miesiaca)
                    brakuje_pracownikowi = cel_godzin - godziny_pracownikow[p.db_id]
                    brakuje_dniowi = 24.0 - suma_godzin_dnia

                    if brakuje_pracownikowi >= 8.0 and brakuje_dniowi >= 8.0:
                        dzien.ustaw_zmiane(p.db_id, "M")
                        godziny_pracownikow[p.db_id] += 8.0
                        suma_godzin_dnia += 8.0
                    elif brakuje_pracownikowi >= 4.0 and brakuje_dniowi >= 4.0:
                        dzien.ustaw_zmiane(p.db_id, "4")
                        godziny_pracownikow[p.db_id] += 4.0
                        suma_godzin_dnia += 4.0

        return True

    def _czy_moze_miec_dzien(self, p_id: int, biezacy_dzien, poprzedni_dzien) -> bool:
        if poprzedni_dzien is None:
            return True
        stary_status = poprzedni_dzien.pobierz_zmiane(p_id)
        if stary_status == "N":
            return False
        return True

    def _czy_moze_miec_noc(self, p_id: int, biezacy_dzien, poprzedni_dzien) -> bool:
        return True
