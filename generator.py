class GeneratorGrafiku:
    """Algorytm "dokańczający" grafik.

    Szanuje wszystkie wpisane już zmiany (D, N, M, 4, UUW, L4, X), uwzględnia
    dozwolone dni pracy pracowników, ich dostępność, ciągłość dni
    przepracowanych, eliminuje 1-dniowe wolne oraz przydziela porę dnia (D/N)
    według preferencji.
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
        elif status == "UUW" and pracownik:
            return pracownik.norma_dobowa(self.norma_miesiaca)
        return 0.0

    def _oblicz_ciag_pracy(self, p_id: int, do_dnia_idx: int) -> int:
        ciag = 0
        for i in range(do_dnia_idx - 1, -1, -1):
            zmiana = self.miesiac.dni[i].pobierz_zmiane(p_id, domyslna="P")
            if zmiana in ["D", "N", "M", "4"]:
                ciag += 1
            else:
                break
        return ciag

    def _czy_tworzy_jednodniowe_wolne(self, p_id: int, biezacy_idx: int) -> bool:
        if biezacy_idx == 0 or biezacy_idx >= len(self.miesiac.dni) - 1:
            return False

        poprzedni = self.miesiac.dni[biezacy_idx - 1].pobierz_zmiane(
            p_id, domyslna="P"
        )
        nastepny_dzien = self.miesiac.dni[biezacy_idx + 1]
        pracownik = next(p for p in self.pracownicy if p.db_id == p_id)

        wczoraj_pracowal = poprzedni in ["D", "N", "M", "4"]
        jutro_musi_pracowac = not pracownik.moze_pracowac_w_dzien(
            nastepny_dzien.data
        )

        return wczoraj_pracowal and jutro_musi_pracowac

    def _preferencja_dnia_tygodnia(self, p_id: int, biezacy_idx: int) -> float:
        """Punktacja preferencji co do samego dnia tygodnia (bez wliczania pory D/N)."""
        pracownik = next(p for p in self.pracownicy if p.db_id == p_id)
        dzien = self.miesiac.dni[biezacy_idx]
        dzien_tygodnia = dzien.data.weekday()

        pref_tyg = getattr(pracownik, "pref_dni_tyg", set())
        if not pref_tyg or dzien_tygodnia in pref_tyg:
            return -1.0  # Premia za preferowany dzień
        return 0.0

    def _oblicz_presje(
        self, pracownik, od_dnia_idx: int, wyrobione_godziny: float
    ) -> float:
        norma_pracownika = pracownik.get_norma_miesiaca(self.norma_miesiaca)
        brakuje_godzin = max(0.0, norma_pracownika - wyrobione_godziny)
        potrzebne_dni = brakuje_godzin / 12.0

        dostepne_dni = sum(
            1
            for dzien in self.miesiac.dni[od_dnia_idx:]
            if pracownik.moze_pracowac_w_dzien(dzien.data)
        )

        if dostepne_dni == 0 or potrzebne_dni <= 0:
            return 0.0

        return -(potrzebne_dni / dostepne_dni)

    def _sortuj_pracownikow_do_pracy(
        self, godziny_pracownikow: dict, biezacy_dzien_idx: int
    ) -> list:
        """Wyznacza ogólną kolejność pracowników do podjęcia PRACY w danym dniu

        (kryteria twarde: brakowanie godzin, ciągłość, presja, preferencje dnia
        tygodnia).
        """
        return sorted(
            self.pracownicy,
            key=lambda p: (
                ( 0 if self._czy_tworzy_jednodniowe_wolne(p.db_id, biezacy_dzien_idx) else 1),
                self._oblicz_ciag_pracy(p.db_id, biezacy_dzien_idx) * 0.4 + self._oblicz_presje(p, biezacy_dzien_idx, godziny_pracownikow[p.db_id]) * 0.8,
                godziny_pracownikow[p.db_id] / p.get_norma_miesiaca(self.norma_miesiaca),
                self._preferencja_dnia_tygodnia(p.db_id, biezacy_dzien_idx),
            ),
        )

    def generuj(self) -> bool:
        godziny_pracownikow = {p.db_id: 0.0 for p in self.pracownicy}

        # 1. Zliczamy godziny z wpisów ręcznych
        for dzien in self.miesiac.dni:
            for p in self.pracownicy:
                stary_status = dzien.pobierz_zmiane(p.db_id, domyslna="P")
                godziny_pracownikow[p.db_id] += self._oblicz_godziny_zmiany(
                    stary_status, p
                )

        # 2. Pętla uzupełniająca brakujące obsady dzień po dniu
        for idx, dzien in enumerate(self.miesiac.dni):
            poprzedni_dzien = self.miesiac.dni[idx - 1] if idx > 0 else None

            suma_godzin_dnia = sum(
                self._oblicz_godziny_zmiany(dzien.pobierz_zmiane(p.db_id), p)
                for p in self.pracownicy
            )

            oblozenie_d = any(
                dzien.pobierz_zmiane(p.db_id) == "D" for p in self.pracownicy
            )
            oblozenie_n = any(
                dzien.pobierz_zmiane(p.db_id) == "N" for p in self.pracownicy
            )

            # --- KROK 1: Wybór candidate-ów na pełne zmiany (D/N) ---
            potrzebne_zmiany_12h = (0 if oblozenie_d else 1) + (
                0 if oblozenie_n else 1
            )

            if potrzebne_zmiany_12h > 0 and suma_godzin_dnia < 24.0:
                kandydaci = []
                kolejnosc = self._sortuj_pracownikow_do_pracy(
                    godziny_pracownikow, idx
                )

                for p in kolejnosc:
                    if len(kandydaci) == potrzebne_zmiany_12h:
                        break

                    if dzien.pobierz_zmiane(p.db_id) != "P":
                        continue
                    if not p.moze_pracowac_w_dzien(dzien.data):
                        continue

                    # Sprawdzamy czy fizycznie może pracować przynajmniej na jednej ze zmian
                    moze_d = (
                        not oblozenie_d
                        and self._czy_moze_miec_dzien(
                            p.db_id, dzien, poprzedni_dzien
                        )
                    )
                    moze_n = (
                        not oblozenie_n
                        and self._czy_moze_miec_noc(
                            p.db_id, dzien, poprzedni_dzien
                        )
                    )

                    if moze_d or moze_n:
                        kandydaci.append(p)

                # --- KROK 2: Dopasowanie wybranych osób wg preferencji pory dnia ---
                if kandydaci:
                    self._przydziel_zmiany_z_preferencjami(
                        dzien,
                        kandydaci,
                        oblozenie_d,
                        oblozenie_n,
                        godziny_pracownikow,
                        poprzedni_dzien,
                    )

                # Odświeżamy stan po obsadzeniu
                oblozenie_d = any(
                    dzien.pobierz_zmiane(p.db_id) == "D"
                    for p in self.pracownicy
                )
                oblozenie_n = any(
                    dzien.pobierz_zmiane(p.db_id) == "N"
                    for p in self.pracownicy
                )
                suma_godzin_dnia = sum(
                    self._oblicz_godziny_zmiany(
                        dzien.pobierz_zmiane(p.db_id), p
                    )
                    for p in self.pracownicy
                )

            # --- KROK 3: Uzupełnianie brakujących godzin (M / 4) ---
            if suma_godzin_dnia < 24.0:
                dostepni_pracownicy = self._sortuj_pracownikow_do_pracy(
                    godziny_pracownikow, idx
                )
                for p in dostepni_pracownicy:
                    if suma_godzin_dnia >= 24.0:
                        break

                    if dzien.pobierz_zmiane(p.db_id) != "P":
                        continue
                    if not p.moze_pracowac_w_dzien(dzien.data):
                        continue

                    cel_godzin = p.get_norma_miesiaca(self.norma_miesiaca)
                    brakuje_pracownikowi = (
                        cel_godzin - godziny_pracownikow[p.db_id]
                    )
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

    def _przydziel_zmiany_z_preferencjami(
        self,
        dzien,
        kandydaci: list,
        oblozenie_d: bool,
        oblozenie_n: bool,
        godziny_pracownikow: dict,
        poprzedni_dzien,
    ):
        """Rozdziela preferencje 'D'/'N' dla wcześniej wyselekcjonowanej grupy kandydatów."""
        wolne_zmiany = []
        if not oblozenie_d:
            wolne_zmiany.append("D")
        if not oblozenie_n:
            wolne_zmiany.append("N")

        # 1. Potrzebna tylko jedna zmiana
        if len(wolne_zmiany) == 1:
            p = kandydaci[0]
            dzien.ustaw_zmiane(p.db_id, wolne_zmiany[0])
            godziny_pracownikow[p.db_id] += 12.0
            return

        # 2. Potrzebne dwie zmiany (D oraz N) dla 2 kandydatów
        if len(kandydaci) >= 2:
            p1, p2 = kandydaci[0], kandydaci[1]

            pref1 = getattr(p1, "pref_pora_dnia", "")
            pref2 = getattr(p2, "pref_pora_dnia", "")

            p1_moze_d = self._czy_moze_miec_dzien(
                p1.db_id, dzien, poprzedni_dzien
            )
            p2_moze_d = self._czy_moze_miec_dzien(
                p2.db_id, dzien, poprzedni_dzien
            )

            # Sytuacja: p1 chce D LUB p2 chce N (i p1 może mieć D)
            if (pref1 == "D" or pref2 == "N") and p1_moze_d:
                dzien.ustaw_zmiane(p1.db_id, "D")
                dzien.ustaw_zmiane(p2.db_id, "N")

            # Sytuacja: p1 chce N LUB p2 chce D (i p2 może mieć D)
            elif (pref1 == "N" or pref2 == "D") and p2_moze_d:
                dzien.ustaw_zmiane(p1.db_id, "N")
                dzien.ustaw_zmiane(p2.db_id, "D")

            # Obaj obojętni (pref1 == "" i pref2 == "")
            else:
                if p1_moze_d:
                    dzien.ustaw_zmiane(p1.db_id, "D")
                    dzien.ustaw_zmiane(p2.db_id, "N")
                else:
                    dzien.ustaw_zmiane(p1.db_id, "N")
                    dzien.ustaw_zmiane(p2.db_id, "D")

            godziny_pracownikow[p1.db_id] += 12.0
            godziny_pracownikow[p2.db_id] += 12.0

    def _czy_moze_miec_dzien(
        self, p_id: int, biezacy_dzien, poprzedni_dzien
    ) -> bool:
        if poprzedni_dzien is None:
            return True
        stary_status = poprzedni_dzien.pobierz_zmiane(p_id)
        if stary_status == "N":
            return False
        return True

    def _czy_moze_miec_noc(
        self, p_id: int, biezacy_dzien, poprzedni_dzien
    ) -> bool:
        return True
