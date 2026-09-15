class GeneratorGrafiku:
    """Algorytm "dokańczający" grafik.

    Szanuje wszystkie wpisane już zmiany (D, N, UUW, L4, X), uwzględnia
    dozwolone dni pracy pracowników, ich dostępność, ciągłość dni
    przepracowanych (preferuje dokładnie 2 dni pracy z rzędu), eliminuje
    1-dniowe wolne oraz równomiernie przydziela porę dnia (D/N).
    """

    def __init__(self, obj_miesiac, obj_miesiac2, pracownicy, norma_miesiaca: float = 160.0):
        self.miesiac = obj_miesiac
        self.poprzedni_miesiac = obj_miesiac2
        self.pracownicy = pracownicy
        self.norma_miesiaca = norma_miesiaca

    def _oblicz_godziny_zmiany(self, status: str, pracownik=None) -> float:
        if status in ["D", "N"]:
            return 12.0
        elif status in ["UUW", "L4", "U", "L"] and pracownik:
            return 8.0 * pracownik.etat
        return 0.0

    def _oblicz_ciag_pracy(self, p_id: int, do_dnia_idx: int) -> int:
        ciag = 0
        for i in range(do_dnia_idx - 1, -1, -1):
            zmiana = self.miesiac.dni[i].pobierz_zmiane(p_id, domyslna="P")
            if zmiana in ["D", "N"]:
                ciag += 1
            else:
                break
        if ciag == do_dnia_idx and self.poprzedni_miesiac and hasattr(self.poprzedni_miesiac, "dni"):
            poprzednie_dni = self.poprzedni_miesiac.dni
            for i in range(len(poprzednie_dni) - 1, -1, -1):
                zmiana = poprzednie_dni[i].pobierz_zmiane(p_id, domyslna="P")
                if zmiana in ["D", "N"]:
                    ciag += 1
                else:
                    break
        return ciag

    def _ocena_ciagu_pracy(self, p_id: int, biezacy_idx: int) -> float:
        """Wyznacza priorytet na podstawie dotychczasowego ciągu pracy:
        - Ciąg = 1 dzień  -> Priorytet 0 (NAJWYŻSZY: domykamy do idealnych 2 dni pracy)
        - Ciąg = 0 dni    -> Priorytet 1 (ŚREDNI: zaczynamy nowy ciąg)
        - Ciąg >= 2 dni   -> Priorytet 10+ (NAJNIŻSZY: unikamy 3+ dni pracy z rzędu)
        """
        ciag = self._oblicz_ciag_pracy(p_id, biezacy_idx)
        if ciag == 1:
            return 0.0
        elif ciag == 0:
            return 1.0
        else:
            return 10.0 + (ciag - 2) * 5.0

    def _preferencja_dnia_tygodnia(self, p_id: int, biezacy_idx: int) -> float:
        pracownik = next(p for p in self.pracownicy if p.db_id == p_id)
        dzien = self.miesiac.dni[biezacy_idx]
        dzien_tygodnia = dzien.data.weekday()

        pref_tyg = getattr(pracownik, "pref_dni_tyg", set())
        if not pref_tyg or dzien_tygodnia in pref_tyg:
            return -1.0
        return 0.0

    def _oblicz_presje(self, pracownik, od_dnia_idx: int, wyrobione_godziny: float) -> float:
        norma_pracownika = pracownik.get_norma_miesiaca(self.norma_miesiaca)
        brakuje_godzin = max(0.0, norma_pracownika - wyrobione_godziny)
        potrzebne_dni = brakuje_godzin / 12.0

        dostepne_dni = sum(1 for dzien in self.miesiac.dni[od_dnia_idx:] if pracownik.moze_pracowac_w_dzien(dzien.data))

        if dostepne_dni == 0 or potrzebne_dni <= 0:
            return 0.0

        return -(potrzebne_dni / dostepne_dni)

    def _czy_przekroczy_norme(self, pracownik, wyrobione_godziny: float, zmiana_godziny: float = 12.0) -> bool:
        norma = pracownik.get_norma_miesiaca(self.norma_miesiaca)
        return (wyrobione_godziny + zmiana_godziny) > norma
    def _czy_moze_miec_dzien(self, p_id: int, biezacy_dzien, poprzedni_dzien) -> bool:
        if poprzedni_dzien is None:
            if self.poprzedni_miesiac and hasattr(self.poprzedni_miesiac, "dni") and self.poprzedni_miesiac.dni:
                ostatni_poprzedni = self.poprzedni_miesiac.dni[-1]
                stary_status = ostatni_poprzedni.pobierz_zmiane(p_id)
                if stary_status == "N":
                    return False
            return True

        stary_status = poprzedni_dzien.pobierz_zmiane(p_id)
        if stary_status == "N":
            return False
        return True

    def _czy_moze_miec_noc(self, p_id: int, biezacy_dzien, nastepny_dzien) -> bool:
        if nastepny_dzien is None:
            return True
        nastepny_status = nastepny_dzien.pobierz_zmiane(p_id)
        if nastepny_status in ["UUW", "D", "X", "L4", "U", "L"]:
            return False
        return True
    def _czy_przekroczy_limit_niedziel(self, p_id: int, biezacy_dzien_idx: int) -> bool:
        dzien = self.miesiac.dni[biezacy_dzien_idx]
        if dzien.data.weekday() != 6:
            return False
        niedziele_wstecz = 0
        for i in range(biezacy_dzien_idx - 1, -1, -1):
            d = self.miesiac.dni[i]
            if d.data.weekday() == 6:  # Jeśli to niedziela
                zmiana = d.pobierz_zmiane(p_id, domyslna="P")
                if zmiana in ["D", "N"]:
                    niedziele_wstecz += 1
                else:
                    break
        if self.poprzedni_miesiac and hasattr(self.poprzedni_miesiac, "dni"):
            for d in reversed(self.poprzedni_miesiac.dni):
                if d.data.weekday() == 6:
                    zmiana = d.pobierz_zmiane(p_id, domyslna="P")
                    if zmiana in ["D", "N"]:
                        niedziele_wstecz += 1
                    else:
                        break
        return niedziele_wstecz >= 3
    def _sortuj_pracownikow_do_pracy(self, godziny_pracownikow: dict, biezacy_dzien_idx: int) -> list:
        return sorted(
            self.pracownicy,
            key=lambda p: (
                # 1. Osoby, które przekroczyły lub osiągnęły normę idą na sam koniec (priorytet 1)
                (1 if godziny_pracownikow[p.db_id] >= p.get_norma_miesiaca(self.norma_miesiaca) else 0),
                # 2. Preferujemy domykanie ciągu 2 dni
                self._ocena_ciagu_pracy(p.db_id, biezacy_dzien_idx),
                # 3. Presja wyrobienia normy
                self._oblicz_presje(p, biezacy_dzien_idx, godziny_pracownikow[p.db_id]),
                # 4. Procent wyrobienia normy (najmniej wyrobieni wyżej)
                godziny_pracownikow[p.db_id] / p.get_norma_miesiaca(self.norma_miesiaca),
                # 5. Preferencja dnia tygodnia
                self._preferencja_dnia_tygodnia(p.db_id, biezacy_dzien_idx),
            ),
        )

    def generuj(self) -> bool:
        godziny_pracownikow = {p.db_id: 0.0 for p in self.pracownicy}
        zrobione_d = {p.db_id: 0 for p in self.pracownicy}
        zrobione_n = {p.db_id: 0 for p in self.pracownicy}

        for dzien in self.miesiac.dni:
            for p in self.pracownicy:
                stary_status = dzien.pobierz_zmiane(p.db_id, domyslna="P")
                godziny_pracownikow[p.db_id] += self._oblicz_godziny_zmiany(stary_status, p)
                if stary_status == "D":
                    zrobione_d[p.db_id] += 1
                elif stary_status == "N":
                    zrobione_n[p.db_id] += 1

        for idx, dzien in enumerate(self.miesiac.dni):
            poprzedni_dzien = self.miesiac.dni[idx - 1] if idx > 0 else None
            nastepny_dzien = self.miesiac.dni[idx + 1] if idx < len(self.miesiac.dni) - 1 else None

            oblozenie_d = any(dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy)
            oblozenie_n = any(dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy)

            potrzebne_zmiany_12h = (0 if oblozenie_d else 1) + (0 if oblozenie_n else 1)

            # --- KROK 1: Wybór osób wg preferencji ---
            if potrzebne_zmiany_12h > 0:
                kandydaci = []
                kolejnosc = self._sortuj_pracownikow_do_pracy(godziny_pracownikow, idx)

                for p in kolejnosc:
                    if len(kandydaci) == potrzebne_zmiany_12h:
                        break

                    if dzien.pobierz_zmiane(p.db_id) != "P":
                        continue

                    if dzien.data.weekday() == 6 and self._czy_przekroczy_limit_niedziel(p.db_id, idx):
                        continue

                    # ZAKAZ OVERTIME: Nie damy zmiany osobie, która przekroczy normę
                    if self._czy_przekroczy_norme(p, godziny_pracownikow[p.db_id], 12.0):
                        continue

                    moze_d = (
                        not oblozenie_d
                        and p.moze_pracowac_w_dzien(dzien.data, pora="D")
                        and self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien)
                    )
                    moze_n = (
                        not oblozenie_n
                        and p.moze_pracowac_w_dzien(dzien.data, pora="N")
                        and self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien)
                    )

                    if moze_d or moze_n:
                        kandydaci.append(p)

                if kandydaci:
                    self._przydziel_zmiany_z_preferencjami(
                        dzien,
                        kandydaci,
                        oblozenie_d,
                        oblozenie_n,
                        godziny_pracownikow,
                        poprzedni_dzien,
                        nastepny_dzien,
                        zrobione_d,
                        zrobione_n,
                    )

            # Odświeżenie stanu obłożenia po KROKU 1
            oblozenie_d = any(dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy)
            oblozenie_n = any(dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy)

            # --- KROK 2: RATUNEK DLA PUSTYCH DNI (Pominięcie preferencji dostępności, ale NADAL BEZ OVERTIME) ---
            if not oblozenie_d or not oblozenie_n:
                kolejnosc_ratunkowa = self._sortuj_pracownikow_do_pracy(godziny_pracownikow, idx)

                if not oblozenie_d:
                    for p in kolejnosc_ratunkowa:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            # Blokada nadgodzin
                            if self._czy_przekroczy_norme(p, godziny_pracownikow[p.db_id], 12.0):
                                continue
                            if self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien):
                                dzien.ustaw_zmiane(p.db_id, "D")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_d[p.db_id] += 1
                                oblozenie_d = True
                                break

                if not oblozenie_n:
                    for p in kolejnosc_ratunkowa:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            # Blokada nadgodzin
                            if self._czy_przekroczy_norme(p, godziny_pracownikow[p.db_id], 12.0):
                                continue
                            if self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien):
                                dzien.ustaw_zmiane(p.db_id, "N")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_n[p.db_id] += 1
                                oblozenie_n = True
                                break

            # Odświeżenie stanu po KROKU 2
            oblozenie_d = any(dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy)
            oblozenie_n = any(dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy)

            # --- KROK 3: OSTATECZNA OBSADA (Jeśli nikt bez nadgodzin nie może pracować, dopuszczamy nadgodziny) ---
            if not oblozenie_d or not oblozenie_n:
                kolejnosc_ostateczna = self._sortuj_pracownikow_do_pracy(godziny_pracownikow, idx)

                if not oblozenie_d:
                    for p in kolejnosc_ostateczna:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            if self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien):
                                dzien.ustaw_zmiane(p.db_id, "D")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_d[p.db_id] += 1
                                oblozenie_d = True
                                break

                if not oblozenie_n:
                    for p in kolejnosc_ostateczna:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            if self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien):
                                dzien.ustaw_zmiane(p.db_id, "N")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_n[p.db_id] += 1
                                oblozenie_n = True
                                break

        return True

    def _przydziel_zmiany_z_preferencjami(
        self,
        dzien,
        kandydaci: list,
        oblozenie_d: bool,
        oblozenie_n: bool,
        godziny_pracownikow: dict,
        poprzedni_dzien,
        nastepny_dzien,
        zrobione_d: dict,
        zrobione_n: dict,
    ):
        wolne_zmiany = []
        if not oblozenie_d:
            wolne_zmiany.append("D")
        if not oblozenie_n:
            wolne_zmiany.append("N")

        if len(wolne_zmiany) == 1:
            zmiana = wolne_zmiany[0]
            for p in kandydaci:
                moze_dostepnosc = p.moze_pracowac_w_dzien(dzien.data, pora=zmiana)
                moze_grafik = (
                    self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien)
                    if zmiana == "D"
                    else self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien)
                )
                if moze_dostepnosc and moze_grafik:
                    dzien.ustaw_zmiane(p.db_id, zmiana)
                    godziny_pracownikow[p.db_id] += 12.0
                    if zmiana == "D":
                        zrobione_d[p.db_id] += 1
                    else:
                        zrobione_n[p.db_id] += 1
                    return
            return

        if len(kandydaci) >= 2:
            p1, p2 = kandydaci[0], kandydaci[1]

            p1_d = p1.moze_pracowac_w_dzien(dzien.data, pora="D") and self._czy_moze_miec_dzien(p1.db_id, dzien, poprzedni_dzien)
            p1_n = p1.moze_pracowac_w_dzien(dzien.data, pora="N") and self._czy_moze_miec_noc(p1.db_id, dzien, nastepny_dzien)

            p2_d = p2.moze_pracowac_w_dzien(dzien.data, pora="D") and self._czy_moze_miec_dzien(p2.db_id, dzien, poprzedni_dzien)
            p2_n = p2.moze_pracowac_w_dzien(dzien.data, pora="N") and self._czy_moze_miec_noc(p2.db_id, dzien, nastepny_dzien)

            opcja_A = p1_d and p2_n  # p1 -> D, p2 -> N
            opcja_B = p1_n and p2_d  # p1 -> N, p2 -> D

            wybrana_opcja = None

            if opcja_A and not opcja_B:
                wybrana_opcja = "A"
            elif opcja_B and not opcja_A:
                wybrana_opcja = "B"
            elif opcja_A and opcja_B:
                score_A, score_B = 0, 0

                pref1 = getattr(p1, "pref_pora_dnia", "")
                pref2 = getattr(p2, "pref_pora_dnia", "")

                if pref1 == "D":
                    score_A += 2
                elif pref1 == "N":
                    score_B += 2

                if pref2 == "N":
                    score_A += 2
                elif pref2 == "D":
                    score_B += 2

                if zrobione_n[p1.db_id] < zrobione_n[p2.db_id]:
                    score_B += 1
                elif zrobione_n[p2.db_id] < zrobione_n[p1.db_id]:
                    score_A += 1

                wybrana_opcja = "A" if score_A >= score_B else "B"

            if wybrana_opcja == "A":
                dzien.ustaw_zmiane(p1.db_id, "D")
                dzien.ustaw_zmiane(p2.db_id, "N")
                godziny_pracownikow[p1.db_id] += 12.0
                godziny_pracownikow[p2.db_id] += 12.0
                zrobione_d[p1.db_id] += 1
                zrobione_n[p2.db_id] += 1
            elif wybrana_opcja == "B":
                dzien.ustaw_zmiane(p1.db_id, "N")
                dzien.ustaw_zmiane(p2.db_id, "D")
                godziny_pracownikow[p1.db_id] += 12.0
                godziny_pracownikow[p2.db_id] += 12.0
                zrobione_n[p1.db_id] += 1
                zrobione_d[p2.db_id] += 1
            else:
                for p in [p1, p2]:
                    if p.moze_pracowac_w_dzien(dzien.data, pora="D") and self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien):
                        dzien.ustaw_zmiane(p.db_id, "D")
                        godziny_pracownikow[p.db_id] += 12.0
                        zrobione_d[p.db_id] += 1
                        break
