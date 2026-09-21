class GeneratorGrafiku:
    """Algorytm "dokańczający" grafik z mechanizmem korekcji końcowej (wyrównywanie godzin)."""

    def __init__(self, obj_miesiac, obj_miesiac2, pracownicy, norma_miesiaca: float = 160.0):
        self.miesiac = obj_miesiac
        self.poprzedni_miesiac = obj_miesiac2
        self.pracownicy = pracownicy
        self.norma_miesiaca = norma_miesiaca

    def _oblicz_godziny_zmiany(self, status: str, pracownik=None) -> float:
        if status in ["D", "N"]:
            return 12.0
        elif status in ["UUW", "L4", "U", "L", "M"] and pracownik:
            return 8.0 * pracownik.etat
        elif status == "4":
            return 4.0
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
        ciag = self._oblicz_ciag_pracy(p_id, biezacy_idx)
        if ciag == 1:
            return 0.0
        elif ciag == 0:
            return 1.0
        elif ciag == 2:
            return 50.0
        else:
            return 500.0 + (ciag - 3) * 100.0

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
                if ostatni_poprzedni.pobierz_zmiane(p_id) == "N":
                    return False
            return True
        if poprzedni_dzien.pobierz_zmiane(p_id) == "N":
            return False
        return True

    def _czy_moze_miec_noc(self, p_id: int, biezacy_dzien, nastepny_dzien) -> bool:
        if nastepny_dzien is None:
            return True
        if nastepny_status := nastepny_dzien.pobierz_zmiane(p_id):
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
            if d.data.weekday() == 6:
                if d.pobierz_zmiane(p_id, domyslna="P") in ["D", "N"]:
                    niedziele_wstecz += 1
                else:
                    break
        if self.poprzedni_miesiac and hasattr(self.poprzedni_miesiac, "dni"):
            for d in reversed(self.poprzedni_miesiac.dni):
                if d.data.weekday() == 6:
                    if d.pobierz_zmiane(p_id, domyslna="P") in ["D", "N"]:
                        niedziele_wstecz += 1
                    else:
                        break
        return niedziele_wstecz >= 3

    def _sortuj_pracownikow_do_pracy(self, godziny_pracownikow: dict, biezacy_dzien_idx: int, zrobione_d: dict, zrobione_n: dict) -> list:
        return sorted(
            self.pracownicy,
            key=lambda p: (
                # 1. Czy przekroczył normę godzinową
                (1 if godziny_pracownikow[p.db_id] >= p.get_norma_miesiaca(self.norma_miesiaca) else 0),

                # 2. Stopień wyrobienia godzin
                godziny_pracownikow[p.db_id] / p.get_norma_miesiaca(self.norma_miesiaca),

                # 4. Ocena ciągu pracy
                self._ocena_ciagu_pracy(p.db_id, biezacy_dzien_idx),

                # 5. Presja godzinowa
                self._oblicz_presje(p, biezacy_dzien_idx, godziny_pracownikow[p.db_id]),

                # 3. Balans D/N. Różnica między N a D.
                (zrobione_n[p.db_id] - zrobione_d[p.db_id]),
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

            # KROK 1: Preferencje
            if potrzebne_zmiany_12h > 0:
                kandydaci = []
                kolejnosc = self._sortuj_pracownikow_do_pracy(godziny_pracownikow, idx, zrobione_d,zrobione_n)

                for p in kolejnosc:
                    if len(kandydaci) == potrzebne_zmiany_12h:
                        break
                    if dzien.pobierz_zmiane(p.db_id) != "P":
                        continue
                    if self._oblicz_ciag_pracy(p.db_id, idx) >= 2:
                        continue
                    if dzien.data.weekday() == 6 and self._czy_przekroczy_limit_niedziel(p.db_id, idx):
                        continue
                    if self._czy_przekroczy_norme(p, godziny_pracownikow[p.db_id], 12.0):
                        continue

                    moze_d = not oblozenie_d and p.moze_pracowac_w_dzien(dzien.data, pora="D") and self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien)
                    moze_n = not oblozenie_n and p.moze_pracowac_w_dzien(dzien.data, pora="N") and self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien)

                    if moze_d or moze_n:
                        kandydaci.append(p)

                if kandydaci:
                    self._przydziel_zmiany_z_preferencjami(dzien, kandydaci, oblozenie_d, oblozenie_n, godziny_pracownikow, poprzedni_dzien, nastepny_dzien, zrobione_d, zrobione_n)

            oblozenie_d = any(dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy)
            oblozenie_n = any(dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy)

            if not oblozenie_d or not oblozenie_n:
                kolejnosc_ratunkowa = self._sortuj_pracownikow_do_pracy(godziny_pracownikow, idx, zrobione_d,zrobione_n)
                if not oblozenie_d:
                    for p in kolejnosc_ratunkowa:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            if self._oblicz_ciag_pracy(p.db_id, idx) >= 2:
                                continue
                            if self._czy_przekroczy_norme(p, godziny_pracownikow[p.db_id], 12.0):
                                continue
                            if self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien):
                                dzien.ustaw_zmiane(p.db_id, "D")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_d[p.db_id] += 1
                                break

                if not oblozenie_n:
                    for p in kolejnosc_ratunkowa:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            if self._oblicz_ciag_pracy(p.db_id, idx) >= 2:
                                continue
                            if self._czy_przekroczy_norme(p, godziny_pracownikow[p.db_id], 12.0):
                                continue
                            if self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien):
                                dzien.ustaw_zmiane(p.db_id, "N")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_n[p.db_id] += 1
                                break

            # KROK 3: Ostateczna obsada
            oblozenie_d = any(dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy)
            oblozenie_n = any(dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy)
            if not oblozenie_d or not oblozenie_n:
                kolejnosc_ostateczna = self._sortuj_pracownikow_do_pracy(godziny_pracownikow, idx, zrobione_d,zrobione_n)
                if not oblozenie_d:
                    for p in kolejnosc_ostateczna:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            if self._oblicz_ciag_pracy(p.db_id, idx) >= 2:
                                continue
                            if self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien):
                                dzien.ustaw_zmiane(p.db_id, "D")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_d[p.db_id] += 1
                                break

                if not oblozenie_n:
                    for p in kolejnosc_ostateczna:
                        if dzien.pobierz_zmiane(p.db_id) == "P":
                            if self._oblicz_ciag_pracy(p.db_id, idx) >= 2:
                                continue
                            if self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien):
                                dzien.ustaw_zmiane(p.db_id, "N")
                                godziny_pracownikow[p.db_id] += 12.0
                                zrobione_n[p.db_id] += 1
                                break

            oblozenie_d = any(dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy)
            oblozenie_n = any(dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy)

            if not oblozenie_d or not oblozenie_n:
                kolejnosc_awaryjna = self._sortuj_pracownikow_do_pracy(godziny_pracownikow, idx, zrobione_d, zrobione_n)
                for p in kolejnosc_awaryjna:
                    if not oblozenie_d and dzien.pobierz_zmiane(p.db_id) == "P":
                        if self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien) and p.moze_pracowac_w_dzien(dzien.data, pora="D"):
                            dzien.ustaw_zmiane(p.db_id, "D")
                            godziny_pracownikow[p.db_id] += 12.0
                            zrobione_d[p.db_id] += 1
                            oblozenie_d = True

                    if not oblozenie_n and dzien.pobierz_zmiane(p.db_id) == "P":
                        if self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien) and p.moze_pracowac_w_dzien(dzien.data, pora="N"):
                            dzien.ustaw_zmiane(p.db_id, "N")
                            godziny_pracownikow[p.db_id] += 12.0
                            zrobione_n[p.db_id] += 1
                            oblozenie_n = True

                    if oblozenie_d and oblozenie_n:
                        break


        # === KROK KOREKCYJNY: Wyrównywanie godzin na sam koniec ===
        self._wyrownaj_godziny()


        return True


    def _wyrownaj_godziny(self):
        """Przechodzi po całym miesiącu i szuka możliwości podmiany zmian,
        aby wyrównać godziny (etat) oraz zbalansować proporcję zmian D (dziennych) i N (nocnych)
        między pracownikami.
        """
        for _ in range(10):
            godziny = {p.db_id: 0.0 for p in self.pracownicy}
            licznik_d = {p.db_id: 0 for p in self.pracownicy}
            licznik_n = {p.db_id: 0 for p in self.pracownicy}

            for dzien in self.miesiac.dni:
                for p in self.pracownicy:
                    stary = dzien.pobierz_zmiane(p.db_id, domyslna="P")
                    godziny[p.db_id] += self._oblicz_godziny_zmiany(stary, p)
                    if stary == "D":
                        licznik_d[p.db_id] += 1
                    elif stary == "N":
                        licznik_n[p.db_id] += 1

            # --- KROK A: Wyrównywanie godzin (tak jak wcześniej) ---
            niedobor_kolejnosc = sorted(
                self.pracownicy,
                key=lambda p: godziny[p.db_id] - p.get_norma_miesiaca(self.norma_miesiaca)
            )

            for biedny in niedobor_kolejnosc:
                norma_biednego = biedny.get_norma_miesiaca(self.norma_miesiaca)
                if godziny[biedny.db_id] >= norma_biednego:
                    continue

                for idx, dzien in enumerate(self.miesiac.dni):
                    if godziny[biedny.db_id] >= norma_biednego:
                        break

                    if dzien.pobierz_zmiane(biedny.db_id) != "P":
                        continue
                    if not biedny.moze_pracowac_w_dzien(dzien.data):
                        continue

                    poprzedni = self.miesiac.dni[idx - 1] if idx > 0 else None
                    nastepny = self.miesiac.dni[idx + 1] if idx < len(self.miesiac.dni) - 1 else None

                    for bogaty in self.pracownicy:
                        if bogaty.db_id == biedny.db_id:
                            continue

                        zmiana_bogatego = dzien.pobierz_zmiane(bogaty.db_id)
                        if zmiana_bogatego not in ["D", "N"]:
                            continue

                        if godziny[bogaty.db_id] <= bogaty.get_norma_miesiaca(self.norma_miesiaca):
                            continue

                        pora = zmiana_bogatego
                        if pora == "D":
                            if not biedny.moze_pracowac_w_dzien(dzien.data, pora="D"):
                                continue
                            if not self._czy_moze_miec_dzien(biedny.db_id, dzien, poprzedni):
                                continue
                        else:
                            if not biedny.moze_pracowac_w_dzien(dzien.data, pora="N"):
                                continue
                            if not self._czy_moze_miec_noc(biedny.db_id, dzien, nastepny):
                                continue

                        dzien.ustaw_zmiane(biedny.db_id, pora)
                        ciag_biednego = self._calc_ciag_dla_korekty(biedny.db_id, idx)
                        dzien.ustaw_zmiane(biedny.db_id, "P")

                        if ciag_biednego > 2:
                            continue

                        dzien.ustaw_zmiane(bogaty.db_id, "P")
                        dzien.ustaw_zmiane(biedny.db_id, pora)

                        godziny[biedny.db_id] += 12.0
                        godziny[bogaty.db_id] -= 12.0
                        if pora == "D":
                            licznik_d[biedny.db_id] += 1
                            licznik_d[bogaty.db_id] -= 1
                        else:
                            licznik_n[biedny.db_id] += 1
                            licznik_n[bogaty.db_id] -= 1
                        break

            # --- KROK B: Wyrównywanie proporcji D / N u osób z wyrobionymi godzinami ---
            for p1 in self.pracownicy:
                sum_p1 = licznik_d[p1.db_id] + licznik_n[p1.db_id]
                if sum_p1 == 0:
                    continue
                proporcja_d_p1 = licznik_d[p1.db_id] / sum_p1

                # Jeśli p1 ma  nadmiar D (np. > 50% zmian to D)
                if proporcja_d_p1 > 0.5:
                    for idx, dzien in enumerate(self.miesiac.dni):
                        if dzien.pobierz_zmiane(p1.db_id) != "D":
                            continue

                        poprzedni = self.miesiac.dni[idx - 1] if idx > 0 else None
                        nastepny = self.miesiac.dni[idx + 1] if idx < len(self.miesiac.dni) - 1 else None

                        for p2 in self.pracownicy:
                            if p1.db_id == p2.db_id:
                                continue
                            if dzien.pobierz_zmiane(p2.db_id) != "N":
                                continue

                            sum_p2 = licznik_d[p2.db_id] + licznik_n[p2.db_id]
                            if sum_p2 == 0:
                                continue
                            proporcja_n_p2 = licznik_n[p2.db_id] / sum_p2
                            if proporcja_n_p2 <= 0.65:
                                continue

                            if not p1.moze_pracowac_w_dzien(dzien.data, pora="N"):
                                continue
                            if not self._czy_moze_miec_noc(p1.db_id, dzien, nastepny):
                                continue

                            if not p2.moze_pracowac_w_dzien(dzien.data, pora="D"):
                                continue
                            if not self._czy_moze_miec_dzien(p2.db_id, dzien, poprzedni):
                                continue

                            # Sprawdzamy ciągi pracy dla obojga przy tej zamianie
                            dzien.ustaw_zmiane(p1.db_id, "N")
                            dzien.ustaw_zmiane(p2.db_id, "D")
                            c1 = self._calc_ciag_dla_korekty(p1.db_id, idx)
                            c2 = self._calc_ciag_dla_korekty(p2.db_id, idx)
                            # Cofamy chwilowo
                            dzien.ustaw_zmiane(p1.db_id, "D")
                            dzien.ustaw_zmiane(p2.db_id, "N")

                            if c1 > 2 or c2 > 2:
                                continue # Ciągi przekroczone

                            dzien.ustaw_zmiane(p1.db_id, "N")
                            dzien.ustaw_zmiane(p2.db_id, "D")

                            licznik_d[p1.db_id] -= 1
                            licznik_n[p1.db_id] += 1
                            licznik_d[p2.db_id] += 1
                            licznik_n[p2.db_id] -= 1
                            break

    def _calc_ciag_dla_korekty(self, p_id: int, idx: int) -> int:
        """Pomocnicza funkcja licząca ciąg pracy z uwzględnieniem stanu w trakcie korekty."""
        return self._oblicz_ciag_pracy(p_id, idx + 1)


    def _przydziel_zmiany_z_preferencjami(
        self, dzien, kandydaci: list, oblozenie_d: bool, oblozenie_n: bool,
        godziny_pracownikow: dict, poprzedni_dzien, nastepny_dzien, zrobione_d: dict, zrobione_n: dict
    ):
        """Przydziela wolne zmiany D i/lub N kandyszatom, dbając o balans D/N."""


        kandydaci_d = sorted(kandydaci, key=lambda p: (zrobione_n[p.db_id] - zrobione_d[p.db_id]), reverse=True)

        kandydaci_n = sorted(kandydaci, key=lambda p: (zrobione_d[p.db_id] - zrobione_n[p.db_id]), reverse=True)

        # Przydzielanie Dniówki
        if not oblozenie_d:
            for p in kandydaci_d:
                if dzien.pobierz_zmiane(p.db_id) == "P":
                    if p.moze_pracowac_w_dzien(dzien.data, pora="D") and self._czy_moze_miec_dzien(p.db_id, dzien, poprzedni_dzien):
                        dzien.ustaw_zmiane(p.db_id, "D")
                        godziny_pracownikow[p.db_id] += 12.0
                        zrobione_d[p.db_id] += 1
                        break
        # Przydzielanie Nocki
        if not oblozenie_n:
            for p in kandydaci_n:
                # Upewniamy się, że nie dostanie nocki ten, komu przed chwilą w tym samym dniu przydzieliliśmy 'D'
                if dzien.pobierz_zmiane(p.db_id) == "P":
                    if p.moze_pracowac_w_dzien(dzien.data, pora="N") and self._czy_moze_miec_noc(p.db_id, dzien, nastepny_dzien):
                        dzien.ustaw_zmiane(p.db_id, "N")
                        godziny_pracownikow[p.db_id] += 12.0
                        zrobione_n[p.db_id] += 1
                        break

