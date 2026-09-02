import calendar
import datetime
import customtkinter as ctk
import pandas as pd
from tkinter import ttk, messagebox, simpledialog

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class Pracownik:
    def __init__(self, imie, nazwisko, wymiar_godzin=160):
        self.imie = imie
        self.nazwisko = nazwisko
        self.wymiar_godzin = float(wymiar_godzin)
        self.wyrobione_godziny = 0.0

    @property
    def pelne_nazwisko(self):
        return f"{self.imie} {self.nazwisko}"

    @property
    def norma_dobowa(self):
        return self.wymiar_godzin / 20.0

    def roznica_godzin(self):
        return self.wyrobione_godziny - self.wymiar_godzin


class DzienPracy:
    dni_tygodnia_pl = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]

    def __init__(self, data: datetime.date):
        self.data = data
        self.dzien_tyg = self.dni_tygodnia_pl[data.weekday()]
        self.czy_roboczy = data.weekday() < 5

    @property
    def sformatowany_dzien(self):
        return f"{self.data.day:02d}\n{self.dzien_tyg}"


class TabelaGrafikApp(ctk.CTk):
    STATUSY = ["P", "D", "N", "UUW", "M", "4", "L4"]

    KOLORY_STATUSOW = {
        "P":   {"fg": "#999999", "btn": "#828282", "hover": "#6e6e6e"}, # Szary hover zamiast granatowego
        "D":   {"fg": "#15803d", "btn": "#166534", "hover": "#14532d"},
        "N":   {"fg": "#0007CD", "btn": "#000594", "hover": "#00035b"},
        "UUW": {"fg": "#b45309", "btn": "#78350f", "hover": "#451a03"},
        "M":   {"fg": "#37D581", "btn": "#1DC069", "hover": "#08A652"},
        "4":   {"fg": "#0284c7", "btn": "#0369a1", "hover": "#075985"},
        "L4":  {"fg": "#b91c1c", "btn": "#991b1b", "hover": "#7f1d1d"}                          # Czerwony (L4)
    }

    MAPA_KLAWISZY = {
        "p": "P",
        "d": "D",
        "n": "N",
        "u": "UUW",
        "m": "M",
        "4": "4",
        "l": "L4"
    }

    KOLOR_DOMYSLNY_FG = ["#3a7ebf", "#1f538d"]
    KOLOR_DOMYSLNY_BTN = ["#36719f", "#14375e"]
    KOLOR_AKTYWNY_FG = "#d97706"
    KOLOR_AKTYWNY_BTN = "#b45309"

    def __init__(self):
        super().__init__()

        self.title("Zbiorczy Grafik - Zamrożone Kolumny + Auto-Scroll")
        self.geometry("1450x720")

        self.pracownicy = [
            Pracownik("Jan", "Kowalski", 160),
            Pracownik("Anna", "Nowak", 160),
            Pracownik("Piotr", "Wiśniewski", 80),
            Pracownik("Katarzyna", "Wójcik", 120)
        ]

        self.dni_miesiaca = []
        self.pola = {}               # (r, c) -> CTkOptionMenu
        self.dane_pól = {}           # (r, c) -> (pracownik, dzien_obj)
        self.etykiety_sum = {}       # pracownik -> CTkLabel
        self.etykiety_sum_dni = {}   # dzien_obj -> CTkLabel

        self.aktywny_kolektyw = (0, 0)

        dzis = datetime.date.today()
        self.wybrany_rok = dzis.year
        self.wybrany_miesiac = dzis.month

        self._zbuduj_ui()
        self._wygeneruj_tabele()

        self.bind_all("<Key>", self._obsluga_klawisza)

    def _zbuduj_ui(self):
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(top_frame, text="Rok:").pack(side="left", padx=(10, 2))
        self.rok_entry = ctk.CTkEntry(top_frame, width=60)
        self.rok_entry.insert(0, str(self.wybrany_rok))
        self.rok_entry.pack(side="left", padx=5)

        ctk.CTkLabel(top_frame, text="Miesiąc:").pack(side="left", padx=(10, 2))
        self.miesiac_option = ctk.CTkOptionMenu(
            top_frame,
            values=[str(i) for i in range(1, 13)],
            width=65,
            command=self._zmiana_daty
        )
        self.miesiac_option.set(str(self.wybrany_miesiac))
        self.miesiac_option.pack(side="left", padx=5)

        btn_zmien_date = ctk.CTkButton(top_frame, text="Zastosuj datę", width=100, command=self._zmiana_daty)
        btn_zmien_date.pack(side="left", padx=5)

        ctk.CTkLabel(top_frame, text=" |  Pracownicy:").pack(side="left", padx=(15, 5))
        btn_add = ctk.CTkButton(top_frame, text="+ Dodaj", width=80, command=self.dodaj_pracownika)
        btn_add.pack(side="left", padx=2)

        btn_del = ctk.CTkButton(top_frame, text="- Usuń", width=80, fg_color="firebrick", command=self.usun_pracownika)
        btn_del.pack(side="left", padx=2)

        # Main Layout container
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=15, pady=5)

        # 1. LEWA SEKCJA (Pracownicy - Stała)
        self.left_frame = ctk.CTkFrame(self.main_container, width=170)
        self.left_frame.pack(side="left", fill="y", padx=(0, 2))
        self.left_frame.pack_propagate(False)

        # 2. ŚRODKOWA SEKCJA (Dni - Przewijana)
        self.center_frame = ctk.CTkFrame(self.main_container)
        self.center_frame.pack(side="left", fill="both", expand=True)

        self.canvas = ctk.CTkCanvas(self.center_frame, highlightthickness=0, bg="#242424")
        self.h_scroll = ttk.Scrollbar(self.center_frame, orient="horizontal", command=self.canvas.xview)

        self.scroll_frame = ctk.CTkFrame(self.canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=self.h_scroll.set)

        self.h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        # 3. PRAWA SEKCJA (Sumy - Stała)
        self.right_frame = ctk.CTkFrame(self.main_container, width=200)
        self.right_frame.pack(side="right", fill="y", padx=(2, 0))
        self.right_frame.pack_propagate(False)

        # Legenda
        legenda_frame = ctk.CTkFrame(self, height=30)
        legenda_frame.pack(fill="x", padx=15, pady=(2, 0))
        ctk.CTkLabel(
            legenda_frame,
            text="Instrukcja:  [Strzałki] = Autoprzesuwanie i nawigacja  |  Imiona i Sumy są ZAMROŻONE  |  [P,D,N,U,M,4,L] = Szybki wpis",
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=10, pady=2)

        btn_save = ctk.CTkButton(legenda_frame, text="Zapisz do Excela", command=self.zapisz_do_excela)
        btn_save.pack(side="right", padx=10, pady=5)

    def _odswiez_kolor_komorki(self, r, c):
        """Aktualizuje kolor komórki na podstawie jej obecnego statusu (o ile nie jest aktywna)."""
        if (r, c) == self.aktywny_kolektyw:
            return

        menu = self.pola[(r, c)]
        status = menu.get()
        kolor_def = self.KOLORY_STATUSOW.get(status, {
            "fg": self.KOLOR_DOMYSLNY_FG,
            "btn": self.KOLOR_DOMYSLNY_BTN,
            "hover": "#1f4b7a"
        })

        menu.configure(
            fg_color=kolor_def["fg"],
            button_color=kolor_def["btn"],
            button_hover_color=kolor_def["hover"]  # <-- TU PODMIENIASZ KOLOR NAJECHANIA
        )

    def _wygeneruj_tabele(self):
        # Czyszczenie ramek
        for w in self.left_frame.winfo_children():
            w.destroy()
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        for w in self.right_frame.winfo_children():
            w.destroy()

        self.pola.clear()
        self.dane_pól.clear()
        self.etykiety_sum.clear()
        self.etykiety_sum_dni.clear()

        liczba_dni = calendar.monthrange(self.wybrany_rok, self.wybrany_miesiac)[1]
        self.dni_miesiaca = [
            DzienPracy(datetime.date(self.wybrany_rok, self.wybrany_miesiac, d))
            for d in range(1, liczba_dni + 1)
        ]

        # --- NAGŁÓWKI ---
        # 1. Lewy nagłówek
        ctk.CTkLabel(self.left_frame, text="Pracownik", font=ctk.CTkFont(weight="bold"), height=35).pack(fill="x", padx=5, pady=5)

        # 2. Środkowy nagłówek (Dni)
        for col_idx, dzien_obj in enumerate(self.dni_miesiaca):
            kolor = "white" if dzien_obj.czy_roboczy else "dodgerblue"
            lbl = ctk.CTkLabel(
                self.scroll_frame,
                text=dzien_obj.sformatowany_dzien,
                text_color=kolor,
                font=ctk.CTkFont(size=11, weight="bold"),
                width=65
            )
            lbl.grid(row=0, column=col_idx, padx=1, pady=5)

        # 3. Prawy nagłówek
        ctk.CTkLabel(self.right_frame, text="Suma godz. / Bilans", font=ctk.CTkFont(weight="bold"), height=35).pack(fill="x", padx=5, pady=5)

        # --- WIERSZE PRACONIKÓW ---
        for r_idx, p in enumerate(self.pracownicy):
            # 1. Lewa strona (Imię i nazwisko)
            lbl_emp = ctk.CTkLabel(self.left_frame, text=f"{p.pelne_nazwisko}", anchor="w", height=28)
            lbl_emp.pack(fill="x", padx=5, pady=3)

            # 2. Środek (Komórki wyboru statusu)
            for c_idx, dzien_obj in enumerate(self.dni_miesiaca):
                opt_menu = ctk.CTkOptionMenu(
                    self.scroll_frame,
                    values=self.STATUSY,
                    width=65,
                    dynamic_resizing=False,
                    command=lambda val, prac=p, d=dzien_obj: self._aktualizuj_stan(prac, d)
                )
                opt_menu.set("P")
                opt_menu.grid(row=r_idx + 1, column=c_idx, padx=1, pady=2)

                self.pola[(r_idx, c_idx)] = opt_menu
                self.dane_pól[(r_idx, c_idx)] = (p, dzien_obj)
                self._odswiez_kolor_komorki(r_idx, c_idx)

                targets = [opt_menu, opt_menu._text_label]
                if hasattr(opt_menu, "_dropdown_callback"):
                    targets.append(opt_menu._dropdown_callback)

                for target in targets:
                    if hasattr(target, "bind"):
                        target.bind("<Button-1>", lambda e, r=r_idx, c=c_idx: self._klikniecie_zaznacz(e, r, c))
                        target.bind("<Double-Button-1>", lambda e, menu=opt_menu: self._otworz_menu(menu))
                        target.bind("<Button-3>", lambda e, menu=opt_menu: self._otworz_menu(menu))

                self.pola[(r_idx, c_idx)] = opt_menu
                self.dane_pól[(r_idx, c_idx)] = (p, dzien_obj)

            # 3. Prawa strona (Suma godzin)
            lbl_sum = ctk.CTkLabel(self.right_frame, text="0 / 0h", font=ctk.CTkFont(size=11, weight="bold"), height=28)
            lbl_sum.pack(fill="x", padx=5, pady=3)
            self.etykiety_sum[p] = lbl_sum

        # --- PODSUMOWANIE DNI (Środkowy panel na dole) ---
        row_sum_idx = len(self.pracownicy) + 1

        # Pusta etykieta po lewej dla wyrównania
        ctk.CTkLabel(self.left_frame, text="", font=ctk.CTkFont(size=10, weight="bold")).pack(fill="x", padx=5, pady=10)

        for col_idx, dzien_obj in enumerate(self.dni_miesiaca):
            lbl_day_sum = ctk.CTkLabel(
                self.scroll_frame,
                text="0 / 0",
                font=ctk.CTkFont(size=10, weight="bold"),
                width=65
            )
            lbl_day_sum.grid(row=row_sum_idx, column=col_idx, padx=1, pady=10)
            self.etykiety_sum_dni[dzien_obj] = lbl_day_sum

        if self.pracownicy and self.dni_miesiaca:
            self._ustaw_aktywny(0, 0)

        self.przelicz_sumy()

    def _otworz_menu(self, opt_menu):
        opt_menu._dropdown_menu.open(opt_menu.winfo_rootx(), opt_menu.winfo_rooty() + opt_menu.winfo_height())

    def _zapewnij_widocznosc(self, r, c):
        """Automatycznie przesuwa poziomy Canvas, gdy aktywna komórka wychodzi poza widoczny kadłub."""
        if (r, c) not in self.pola:
            return

        self.update_idletasks()

        widget = self.pola[(r, c)]
        total_width = self.scroll_frame.winfo_width()

        if total_width <= 0:
            return

        x = widget.winfo_x()
        w = widget.winfo_width()

        x_left, x_right = self.canvas.xview()

        vis_x_left = x_left * total_width
        vis_x_right = x_right * total_width

        if x < vis_x_left:
            new_x = x / total_width
            self.canvas.xview_moveto(new_x)
        elif x + w > vis_x_right:
            new_x = (x + w - (vis_x_right - vis_x_left)) / total_width
            self.canvas.xview_moveto(new_x)

    def _ustaw_aktywny(self, r, c):
        old_r, old_c = self.aktywny_kolektyw
        self.aktywny_kolektyw = (r, c)

        # Przywróć dedykowany kolor poprzedniej komórce
        if (old_r, old_c) in self.pola:
            self._odswiez_kolor_komorki(old_r, old_c)

        # Ustaw kolor aktywnego zaznaczenia dla nowej komórki
        if (r, c) in self.pola:
            self.pola[(r, c)].configure(
                fg_color=self.KOLOR_AKTYWNY_FG,
                button_color=self.KOLOR_AKTYWNY_BTN
            )
            self.pola[(r, c)].focus_set()
            self._zapewnij_widocznosc(r, c)

    def _klikniecie_zaznacz(self, event, r, c):
        self._ustaw_aktywny(r, c)
        return "break"

    def _obsluga_klawisza(self, event):
        if self.focus_get() == self.rok_entry:
            return

        r, c = self.aktywny_kolektyw
        max_r = len(self.pracownicy) - 1
        max_c = len(self.dni_miesiaca) - 1

        key = event.keysym.lower()
        char = event.char.lower()

        if key == "up":
            r = max(0, r - 1)
        elif key == "down":
            r = min(max_r, r + 1)
        elif key == "left":
            c = max(0, c - 1)
        elif key == "right":
            c = min(max_c, c + 1)

        elif key in ["space", "return"]:
            self._przelacz_nastepny_status(r, c)
            return "break"

        elif char in self.MAPA_KLAWISZY:
            nowy_status = self.MAPA_KLAWISZY[char]
            self._ustaw_status(r, c, nowy_status)
            return "break"

        if (r, c) != self.aktywny_kolektyw:
            self._ustaw_aktywny(r, c)
            return "break"

    def _przelacz_nastepny_status(self, r, c):
        menu = self.pola[(r, c)]
        obecny = menu.get()
        idx = (self.STATUSY.index(obecny) + 1) % len(self.STATUSY)
        nowy_status = self.STATUSY[idx]
        self._ustaw_status(r, c, nowy_status)

    def _ustaw_status(self, r, c, nowy_status):
        menu = self.pola[(r, c)]
        menu.set(nowy_status)
        prac, dzien_obj = self.dane_pól[(r, c)]
        self._aktualizuj_stan(prac, dzien_obj)

    def _zlicz_stany(self, pracownik: Pracownik):
        licznik = {"D": 0, "N": 0, "UUW": 0, "L4": 0}
        for dzien_obj in self.dni_miesiaca:
            for (r, c), (p, d) in self.dane_pól.items():
                if p == pracownik and d == dzien_obj:
                    stan = self.pola[(r, c)].get()
                    if stan in licznik:
                        licznik[stan] += 1
        return licznik

    def _przelicz_pracownika(self, pracownik: Pracownik):
        suma_godzin = 0.0

        for (r, c), (p, dzien_obj) in self.dane_pól.items():
            if p == pracownik:
                stan = self.pola[(r, c)].get()
                if stan == "UUW":
                    suma_godzin += pracownik.norma_dobowa
                elif stan in ["D", "N"]:
                    suma_godzin += 12.0
                elif stan == "M":
                    suma_godzin += 8.0
                elif stan == "4":
                    suma_godzin += 4.0

        pracownik.wyrobione_godziny = suma_godzin

        roznica = pracownik.roznica_godzin()
        suma_str = f"{int(suma_godzin)}" if suma_godzin.is_integer() else f"{suma_godzin:.1f}"

        stany = self._zlicz_stany(pracownik)
        stany_str = f"D:{stany['D']} | N:{stany['N']} | U:{stany['UUW']} | L:{stany['L4']}"

        tekst = f"{suma_str}/{int(pracownik.wymiar_godzin)}h -> {stany_str}"
        if pracownik in self.etykiety_sum:
            self.etykiety_sum[pracownik].configure(text=tekst)

    def _przelicz_dzien(self, dzien_obj: DzienPracy):
        obstawione_godziny = 0.0

        for (r, c), (pracownik, d) in self.dane_pól.items():
            if d == dzien_obj:
                stan = self.pola[(r, c)].get()
                if stan in ["D", "N"]:
                    obstawione_godziny += 12.0
                elif stan == "M":
                    obstawione_godziny += 8.0
                elif stan == "4":
                    obstawione_godziny += 4.0

        wymagane_godziny = 24.0

        obs_str = f"{int(obstawione_godziny)}" if obstawione_godziny.is_integer() else f"{obstawione_godziny:.1f}"
        wym_str = f"{int(wymagane_godziny)}" if wymagane_godziny.is_integer() else f"{wymagane_godziny:.1f}"

        tekst = f"{obs_str}\n/ {wym_str}h"

        if obstawione_godziny >= wymagane_godziny and wymagane_godziny > 0:
            kolor = "#2ea043"
        elif obstawione_godziny < wymagane_godziny:
            kolor = "#d97706"
        else:
            kolor = "gray"

        if dzien_obj in self.etykiety_sum_dni:
            self.etykiety_sum_dni[dzien_obj].configure(text=tekst, text_color=kolor)

    def _aktualizuj_stan(self, pracownik: Pracownik, dzien_obj: DzienPracy):
        self._przelicz_pracownika(pracownik)
        self._przelicz_dzien(dzien_obj)

    def przelicz_sumy(self):
        for p in self.pracownicy:
            self._przelicz_pracownika(p)
        for d in self.dni_miesiaca:
            self._przelicz_dzien(d)



    def _zmiana_daty(self, *args):
        try:
            self.wybrany_rok = int(self.rok_entry.get())
            self.wybrany_miesiac = int(self.miesiac_option.get())
            self._wygeneruj_tabele()
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawny rok.")

    def dodaj_pracownika(self):
        imie = simpledialog.askstring("Nowy Pracownik", "Wpisz imię:")
        if not imie:
            return
        nazwisko = simpledialog.askstring("Nowy Pracownik", "Wpisz nazwisko:")
        if not nazwisko:
            return
        wymiar = simpledialog.askstring("Wymiar godzin", "Wprowadź miesięczną normę etatu (np. 160 dla 1.0, 80 dla 0.5):", initialvalue="160")

        try:
            wymiar_val = float(wymiar) if wymiar else 160.0
            nowy = Pracownik(imie.strip(), nazwisko.strip(), wymiar_val)
            self.pracownicy.append(nowy)
            self._wygeneruj_tabele()
        except ValueError:
            messagebox.showerror("Błąd", "Niepoprawna wartość wymiaru godzin.")

    def usun_pracownika(self):
        if not self.pracownicy:
            return
        opcje = [p.pelne_nazwisko for p in self.pracownicy]
        wybor = simpledialog.askstring("Usuń Pracownika", f"Wpisz nazwisko do usunięcia:\n({', '.join(opcje)})")

        if wybor:
            self.pracownicy = [p for p in self.pracownicy if p.pelne_nazwisko != wybor.strip() and p.nazwisko != wybor.strip()]
            self._wygeneruj_tabele()

    def zapisz_do_excela(self):
        self.przelicz_sumy()

        rows = []
        for p in self.pracownicy:
            stany = self._zlicz_stany(p)
            row_data = {
                "Imię": p.imie,
                "Nazwisko": p.nazwisko,
                "Norma (h)": p.wymiar_godzin
            }
            for dzien_obj in self.dni_miesiaca:
                stan = "P"
                for (r, c), (prac, d) in self.dane_pól.items():
                    if prac == p and d == dzien_obj:
                        stan = self.pola[(r, c)].get()
                        break
                naglowek_excel = f"{dzien_obj.data.day:02d}.{dzien_obj.data.month:02d} ({dzien_obj.dzien_tyg})"
                row_data[naglowek_excel] = stan

            row_data["Suma godz."] = p.wyrobione_godziny
            row_data["Bilans (h)"] = p.roznica_godzin()
            row_data["D (dni)"] = stany["D"]
            row_data["N (dni)"] = stany["N"]
            row_data["UUW (dni)"] = stany["UUW"]
            row_data["L4 (dni)"] = stany["L4"]
            rows.append(row_data)

        row_dzien_sum = {
            "Imię": "PODSUMOWANIE",
            "Nazwisko": "OBSADA (h)",
            "Norma (h)": ""
        }
        for dzien_obj in self.dni_miesiaca:
            obstawione = 0.0
            for (r, c), (p, d) in self.dane_pól.items():
                if d == dzien_obj:
                    stan = self.pola[(r, c)].get()
                    if stan in ["D", "N"]:
                        obstawione += 12.0
                    elif stan == "M":
                        obstawione += 8.0
                    elif stan == "4":
                        obstawione += 4.0
                    elif stan == "UUW":
                        obstawione += p.norma_dobowa

            naglowek_excel = f"{dzien_obj.data.day:02d}.{dzien_obj.data.month:02d} ({dzien_obj.dzien_tyg})"
            row_dzien_sum[naglowek_excel] = obstawione

        rows.append(row_dzien_sum)

        df = pd.DataFrame(rows)
        filename = f"grafik_stany_{self.wybrany_rok}_{self.wybrany_miesiac:02d}.xlsx"

        try:
            df.to_excel(filename, index=False)
            messagebox.showinfo("Sukces", f"Zapisano grafik ze stanami w pliku:\n{filename}")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Błąd podczas zapisu do Excela: {e}")


if __name__ == "__main__":
    app = TabelaGrafikApp()
    app.mainloop()
