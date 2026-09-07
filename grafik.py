import calendar
import datetime
import os
import customtkinter as ctk
import pandas as pd
from tkinter import ttk, messagebox, simpledialog, filedialog

import sqlite3

from baza import Pracownik, db_aktualizuj_pracownika, db_dodaj_pracownika, init_db, Miesiac, db_pobierz_pracownikow, db_usun_pracownika, DzienPracy
from generator import GeneratorGrafiku


class OknoEdycjiPracownika(ctk.CTkToplevel):
    """Okno dialogowe do dodawania i edycji danych pracownika z wyborem dni miesiąca oraz importem CSV."""

    def __init__(self, parent, pracownik: Pracownik = None, max_dni_miesiaca: int = 31):
        super().__init__(parent)
        self.parent = parent
        self.pracownik = pracownik
        self.max_dni = max_dni_miesiaca
        self.wynik = False

        self.title("Edycja Pracownika" if pracownik else "Dodaj Pracownika")
        self.geometry("420x560")
        self.resizable(False, False)
        self.grab_set()

        self._zbuduj_formularz()

    def _zbuduj_formularz(self):
        ctk.CTkLabel(self, text="Imię:").pack(anchor="w", padx=20, pady=(10, 2))
        self.entry_imie = ctk.CTkEntry(self, width=380)
        self.entry_imie.pack(padx=20)
        if self.pracownik:
            self.entry_imie.insert(0, self.pracownik.imie)

        ctk.CTkLabel(self, text="Nazwisko:").pack(anchor="w", padx=20, pady=(5, 2))
        self.entry_nazwisko = ctk.CTkEntry(self, width=380)
        self.entry_nazwisko.pack(padx=20)
        if self.pracownik:
            self.entry_nazwisko.insert(0, self.pracownik.nazwisko)

        ctk.CTkLabel(self, text="Wymiar etatu (np. 1.0, 0.5):").pack(anchor="w", padx=20, pady=(5, 2))
        self.entry_etat = ctk.CTkEntry(self, width=380)
        self.entry_etat.pack(padx=20)
        self.entry_etat.insert(0, str(self.pracownik.etat) if self.pracownik else "1.0")

        # Nagłówek i przycisk importu z CSV
        frame_header_dni = ctk.CTkFrame(self, fg_color="transparent")
        frame_header_dni.pack(fill="x", padx=20, pady=(10, 2))

        ctk.CTkLabel(frame_header_dni, text="Dozwolone dni miesiąca:").pack(side="left")
        ctk.CTkButton(
            frame_header_dni,
            text="Wczytaj z CSV",
            width=110,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._importuj_z_csv
        ).pack(side="right")

        # Scrollable Frame na numery dni
        self.frame_scroll_dni = ctk.CTkScrollableFrame(self, height=180)
        self.frame_scroll_dni.pack(fill="x", padx=20, pady=5)

        self.checkboxy_dni = {}
        cols = 6
        for dzien in range(1, self.max_dni + 1):
            domyslny_stan = (dzien in self.pracownik.dni_pracy) if self.pracownik else True
            var = ctk.BooleanVar(value=domyslny_stan)
            chk = ctk.CTkCheckBox(self.frame_scroll_dni, text=str(dzien), variable=var, width=50)
            r = (dzien - 1) // cols
            c = (dzien - 1) % cols
            chk.grid(row=r, column=c, padx=3, pady=3, sticky="w")
            self.checkboxy_dni[dzien] = var

        # Przyciski Zaznacz/Odznacz wszystko
        frame_quick = ctk.CTkFrame(self, fg_color="transparent")
        frame_quick.pack(fill="x", padx=20, pady=2)
        ctk.CTkButton(frame_quick, text="Zaznacz wszystkie", width=120, fg_color="gray", command=lambda: self._zmien_wszystkie(True)).pack(side="left")
        ctk.CTkButton(frame_quick, text="Odznacz wszystkie", width=120, fg_color="gray", command=lambda: self._zmien_wszystkie(False)).pack(side="right")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkButton(btn_frame, text="Zapisz", fg_color="#16a34a", hover_color="#15803d", command=self._zapisz).pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="Anuluj", fg_color="gray", command=self.destroy).pack(side="right", padx=5)

    def _zmien_wszystkie(self, stan: bool):
        for var in self.checkboxy_dni.values():
            var.set(stan)

    def _importuj_z_csv(self):
        filepath = filedialog.askopenfilename(
            title="Wybierz plik CSV z dniami pracy",
            filetypes=[("Pliki CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
            parent=self
        )
        if not filepath:
            return

        try:
            # Wczytywanie pliku CSV
            df = pd.read_csv(filepath)

            pobrane_dni = []
            # Próba znalezienia kolumny wskazującej dzień
            kolumny = [col.lower().strip() for col in df.columns]
            target_col = None
            for c in df.columns:
                if c.lower().strip() in ["dzien", "dzień", "day", "dni"]:
                    target_col = c
                    break

            if target_col:
                pobrane_dni = df[target_col].dropna().tolist()
            else:
                # Jeśli brak pasującej nazwy kolumny, pobieramy wszystkie liczby z pliku
                pobrane_dni = df.iloc[:, 0].dropna().tolist()

            wyselekcjonowane = set()
            for val in pobrane_dni:
                try:
                    # Próba konwersji na int lub wyciągnięcie dnia z daty
                    if isinstance(val, str) and "-" in val:
                        val = datetime.datetime.strptime(val.strip(), "%Y-%m-%d").day
                    d_int = int(float(val))
                    if 1 <= d_int <= 31:
                        wyselekcjonowane.add(d_int)
                except ValueError:
                    continue

            if not wyselekcjonowane:
                messagebox.showwarning("Informacja", "Nie udało się odczytać prawidłowych dni z pliku CSV.", parent=self)
                return

            # Aktualizacja checkboksów
            for d, var in self.checkboxy_dni.items():
                var.set(d in wyselekcjonowane)

            messagebox.showinfo("Sukces", f"Pomyślnie zaimportowano {len(wyselekcjonowane)} dni z pliku CSV.", parent=self)

        except Exception as e:
            messagebox.showerror("Błąd pliku", f"Błąd podczas odczytu pliku CSV:\n{e}", parent=self)

    def _zapisz(self):
        imie = self.entry_imie.get().strip()
        nazwisko = self.entry_nazwisko.get().strip()
        etat_str = self.entry_etat.get().replace(",", ".").strip()

        if not imie or not nazwisko:
            messagebox.showerror("Błąd", "Imię i nazwisko nie mogą być puste.", parent=self)
            return

        try:
            etat = float(etat_str)
            if etat <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawną część etatu (np. 1.0, 0.5).", parent=self)
            return

        wybrane_dni = [str(d) for d, var in self.checkboxy_dni.items() if var.get()]
        if not wybrane_dni:
            messagebox.showerror("Błąd", "Zaznacz co najmniej jeden dzień pracy.", parent=self)
            return

        dni_pracy_str = ",".join(wybrane_dni)

        if self.pracownik:
            db_aktualizuj_pracownika(self.pracownik.db_id, imie, nazwisko, etat, dni_pracy_str)
        else:
            db_dodaj_pracownika(imie, nazwisko, etat, dni_pracy_str)

        self.wynik = True
        self.destroy()


class TabelaGrafikApp(ctk.CTk):
    STATUSY = ["P", "D", "N", "UUW", "M", "4", "L4", "X"]

    KOLORY_STATUSOW = {
        "P": {"fg": "#999999", "btn": "#828282", "hover": "#6e6e6e"},
        "D": {"fg": "#15803d", "btn": "#166534", "hover": "#14532d"},
        "N": {"fg": "#0007CD", "btn": "#000594", "hover": "#00035b"},
        "UUW": {"fg": "#b45309", "btn": "#78350f", "hover": "#451a03"},
        "M": {"fg": "#37D581", "btn": "#1DC069", "hover": "#08A652"},
        "4": {"fg": "#0284c7", "btn": "#0369a1", "hover": "#075985"},
        "L4": {"fg": "#b91c1c", "btn": "#991b1b", "hover": "#7f1d1d"},
        "X": {"fg": "#895089", "btn": "#704570", "hover": "#513251"}
    }

    MAPA_KLAWISZY = {
        "p": "P", "d": "D", "n": "N", "u": "UUW",
        "m": "M", "4": "4", "l": "L4", "x": "X"
    }

    KOLOR_DOMYSLNY_FG = ["#3a7ebf", "#1f538d"]
    KOLOR_DOMYSLNY_BTN = ["#36719f", "#14375e"]
    KOLOR_AKTYWNY_FG = "#d97706"
    KOLOR_AKTYWNY_BTN = "#b45309"

    def __init__(self):
        super().__init__()

        self.title("Zbiorczy Grafik")
        self.geometry("1450x720")

        os.makedirs("grafiki", exist_ok=True)
        init_db()

        dzis = datetime.date.today()
        self.wybrany_rok = dzis.year
        self.wybrany_miesiac = dzis.month
        self.norma_miesiaca = 160.0

        self.obj_miesiac = Miesiac(self.wybrany_rok, self.wybrany_miesiac, self.norma_miesiaca)

        self.pracownicy = self._wczytaj_pracownikow_z_bazy()

        self.pola = {}
        self.dane_pól = {}
        self.etykiety_sum = {}
        self.etykiety_sum_dni = {}

        self.aktywny_kolektyw = (0, 0)

        self._zbuduj_ui()
        self._wygeneruj_tabele()

        self.bind_all("<Key>", self._obsluga_klawisza)

    def _wczytaj_pracownikow_z_bazy(self):
        rekordy = db_pobierz_pracownikow()
        if not rekordy:
            domyslne = [
                ("Jan", "Kowalski", 1.0, "0,1,2,3,4"),
                ("Anna", "Nowak", 1.0, "0,1,2,3,4,5,6"),
                ("Piotr", "Wiśniewski", 0.5, "0,1,2,3,4"),
                ("Katarzyna", "Wójcik", 0.75, "0,1,2,3,4,5,6")
            ]
            for imie, nazwisko, etat, dni in domyslne:
                db_dodaj_pracownika(imie, nazwisko, etat, dni)
            rekordy = db_pobierz_pracownikow()

        return [
            Pracownik(p[1], p[2], p[3], dni_pracy=p[4], db_id=p[0])
            for p in rekordy
        ]

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

        ctk.CTkLabel(top_frame, text=" |  wymiar godzin:").pack(side="left", padx=(10, 2))
        self.norma_miesiaca_entry = ctk.CTkEntry(top_frame, width=60)
        self.norma_miesiaca_entry.insert(0, f"{int(self.norma_miesiaca) if self.norma_miesiaca.is_integer() else self.norma_miesiaca}")
        self.norma_miesiaca_entry.pack(side="left", padx=5)

        btn_update_norma = ctk.CTkButton(top_frame, text="Przelicz", width=65, command=self._zaktualizuj_norme_miesiaca)
        btn_update_norma.pack(side="left", padx=2)

        ctk.CTkLabel(top_frame, text=" |  Pracownicy:").pack(side="left", padx=(15, 5))
        btn_add = ctk.CTkButton(top_frame, text="+ Dodaj", width=75, command=self.dodaj_pracownika)
        btn_add.pack(side="left", padx=2)

        btn_edit = ctk.CTkButton(top_frame, text="Edytuj", width=75, command=self.edytuj_zaznaczonego_pracownika)
        btn_edit.pack(side="left", padx=2)

        btn_del = ctk.CTkButton(top_frame, text="Usuń", width=75, fg_color="firebrick", command=self.usun_pracownika)
        btn_del.pack(side="left", padx=2)

        btn_auto = ctk.CTkButton(
            top_frame,
            text="Auto Grafik",
            width=100,
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self.automatycznie_generuj_grafik
        )
        btn_auto.pack(side="left", padx=(15, 2))

        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=15, pady=5)

        self.left_frame = ctk.CTkFrame(self.main_container, width=170)
        self.left_frame.pack(side="left", fill="y", padx=(0, 2))
        self.left_frame.pack_propagate(False)

        self.center_frame = ctk.CTkFrame(self.main_container)
        self.center_frame.pack(side="left", fill="both", expand=True, pady=(15, 0))

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

        self.right_frame = ctk.CTkFrame(self.main_container, width=260)
        self.right_frame.pack(side="right", fill="y", padx=(2, 0))
        self.right_frame.pack_propagate(False)

        legenda_frame = ctk.CTkFrame(self, height=30)
        legenda_frame.pack(fill="x", padx=15, pady=(2, 0))
        ctk.CTkLabel(
            legenda_frame,
            text="Instrukcja:  [Podwójne kliknięcie na imię] = Edycja pracownika | [Strzałki] = Nawigacja",
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=10, pady=2)

        btn_save = ctk.CTkButton(legenda_frame, text="Zapisz do Excela", command=self.zapisz_do_excela)
        btn_save.pack(side="right", padx=10, pady=5)

    def _zaktualizuj_norme_miesiaca(self):
        try:
            val = float(self.norma_miesiaca_entry.get().replace(",", "."))
            if val <= 0:
                raise ValueError
            self.norma_miesiaca = val
            self.obj_miesiac.norma_miesiaca = val
            self.przelicz_sumy()
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawną dodatnią liczbę dla normy miesięcznej.", parent=self)

    def _odswiez_kolor_komorki(self, r, c):
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
            button_hover_color=kolor_def["hover"]
        )

    def _wygeneruj_tabele(self):
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

        ctk.CTkLabel(self.left_frame, text="Pracownik", font=ctk.CTkFont(weight="bold"), height=35).pack(fill="x", padx=5, pady=5)

        for col_idx, dzien_obj in enumerate(self.obj_miesiac.dni):
            kolor = "white" if dzien_obj.czy_roboczy else "dodgerblue"
            lbl = ctk.CTkLabel(
                self.scroll_frame,
                text=dzien_obj.sformatowany_dzien,
                text_color=kolor,
                font=ctk.CTkFont(size=11, weight="bold"),
                width=65
            )
            lbl.grid(row=0, column=col_idx, padx=1, pady=5)

        ctk.CTkLabel(self.right_frame, text="Suma godz. / Bilans", font=ctk.CTkFont(weight="bold"), height=35).pack(fill="x", padx=5, pady=5)

        for r_idx, p in enumerate(self.pracownicy):
            lbl_emp = ctk.CTkLabel(self.left_frame, text=p.pelne_nazwisko, anchor="w", height=28, cursor="hand2")
            lbl_emp.pack(fill="x", padx=5, pady=3)
            # Podwójne kliknięcie na pracownika otwiera edycję
            lbl_emp.bind("<Double-Button-1>", lambda e, prac=p: self._otworz_edycje_pracownika(prac))

            for c_idx, dzien_obj in enumerate(self.obj_miesiac.dni):
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

                targets = [opt_menu, opt_menu._text_label]
                if hasattr(opt_menu, "_dropdown_callback"):
                    targets.append(opt_menu._dropdown_callback)

                for target in targets:
                    if hasattr(target, "bind"):
                        target.bind("<Button-1>", lambda e, r=r_idx, c=c_idx: self._klikniecie_zaznacz(e, r, c))
                        target.bind("<Double-Button-1>", lambda e, menu=opt_menu: self._otworz_menu(menu))
                        target.bind("<Button-3>", lambda e, menu=opt_menu: self._otworz_menu(menu))

            lbl_sum = ctk.CTkLabel(self.right_frame, text="0 / 0h", font=ctk.CTkFont(size=11, weight="bold"), height=28)
            lbl_sum.pack(fill="x", padx=5, pady=3)
            self.etykiety_sum[p] = lbl_sum

        row_sum_idx = len(self.pracownicy) + 1

        ctk.CTkLabel(self.left_frame, text="", font=ctk.CTkFont(size=10, weight="bold")).pack(fill="x", padx=5, pady=10)

        for col_idx, dzien_obj in enumerate(self.obj_miesiac.dni):
            lbl_day_sum = ctk.CTkLabel(
                self.scroll_frame,
                text="0 / 0",
                font=ctk.CTkFont(size=10, weight="bold"),
                width=65
            )
            lbl_day_sum.grid(row=row_sum_idx, column=col_idx, padx=1, pady=10)
            self.etykiety_sum_dni[dzien_obj] = lbl_day_sum

        self.wczytaj_z_excela()

        if (0, 0) in self.pola:
            self._ustaw_aktywny(0, 0)

        self.przelicz_sumy()

    def _otworz_edycje_pracownika(self, pracownik: Pracownik):
        okno = OknoEdycjiPracownika(self, pracownik)
        self.wait_window(okno)
        if okno.wynik:
            self.pracownicy = self._wczytaj_pracownikow_z_bazy()
            self._wygeneruj_tabele()

    def edytuj_zaznaczonego_pracownika(self):
        if not self.pracownicy:
            return
        r, _ = self.aktywny_kolektyw
        if 0 <= r < len(self.pracownicy):
            self._otworz_edycje_pracownika(self.pracownicy[r])

    def dodaj_pracownika(self):
        okno = OknoEdycjiPracownika(self)
        self.wait_window(okno)
        if okno.wynik:
            self.pracownicy = self._wczytaj_pracownikow_z_bazy()
            self._wygeneruj_tabele()

    def usun_pracownika(self):
        if not self.pracownicy:
            return
        opcje = [p.pelne_nazwisko for p in self.pracownicy]

        wybor = simpledialog.askstring(
            "Usuń Pracownika",
            f"Wpisz imię i nazwisko lub nazwisko do usunięcia:\n({', '.join(opcje)})",
            parent=self
        )
        if wybor:
            wybor_clean = wybor.strip()
            do_usuniecia = None

            for p in self.pracownicy:
                if p.pelne_nazwisko == wybor_clean or p.nazwisko == wybor_clean:
                    do_usuniecia = p
                    break

            if do_usuniecia:
                db_usun_pracownika(do_usuniecia.db_id)
                self.pracownicy = self._wczytaj_pracownikow_z_bazy()
                self._wygeneruj_tabele()
            else:
                messagebox.showwarning("Informacja", "Nie znaleziono podanego pracownika.", parent=self)

    def _otworz_menu(self, opt_menu):
        opt_menu._dropdown_menu.open(opt_menu.winfo_rootx(), opt_menu.winfo_rooty() + opt_menu.winfo_height())

    def _zapewnij_widocznosc(self, r, c):
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
            self.canvas.xview_moveto(x / total_width)
        elif x + w > vis_x_right:
            self.canvas.xview_moveto((x + w - (vis_x_right - vis_x_left)) / total_width)

    def _ustaw_aktywny(self, r, c):
        if (r, c) not in self.pola:
            return

        old_r, old_c = self.aktywny_kolektyw
        self.aktywny_kolektyw = (r, c)

        if (old_r, old_c) in self.pola:
            self._odswiez_kolor_komorki(old_r, old_c)

        if (r, c) in self.pola:
            self.pola[(r, c)].configure(
                fg_color=self.KOLOR_AKTYWNY_FG,
                button_color=self.KOLOR_AKTYWNY_BTN
            )
            self.pola[(r, c)].focus_set()
            self._zapewnij_widocznosc(r, c)

    def _przelacz_nastepny_status(self, r, c):
        if (r, c) not in self.pola:
            return
        menu = self.pola[(r, c)]
        idx = (self.STATUSY.index(menu.get()) + 1) % len(self.STATUSY)
        self._ustaw_status(r, c, self.STATUSY[idx])

    def _ustaw_status(self, r, c, nowy_status):
        if (r, c) not in self.pola:
            return
        menu = self.pola[(r, c)]
        menu.set(nowy_status)
        prac, dzien_obj = self.dane_pól[(r, c)]
        self._aktualizuj_stan(prac, dzien_obj)

    def _klikniecie_zaznacz(self, event, r, c):
        self._ustaw_aktywny(r, c)
        return "break"

    def _obsluga_klawisza(self, event):
        if self.focus_get() in [self.rok_entry, self.norma_miesiaca_entry]:
            return

        r, c = self.aktywny_kolektyw
        max_r = len(self.pracownicy) - 1
        max_c = len(self.obj_miesiac.dni) - 1

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
            self._ustaw_status(r, c, self.MAPA_KLAWISZY[char])
            return "break"

        if (r, c) != self.aktywny_kolektyw:
            self._ustaw_aktywny(r, c)
            return "break"

    def _zlicz_stany(self, pracownik: Pracownik):
        licznik = {"D": 0, "N": 0, "UUW": 0, "L4": 0, "M": 0, "4": 0, "X": 0}
        for dzien_obj in self.obj_miesiac.dni:
            stan = dzien_obj.pobierz_zmiane(pracownik.db_id)
            if stan in licznik:
                licznik[stan] += 1
        return licznik

    def _przelicz_pracownika(self, pracownik: Pracownik):
        suma_godzin = 0.0

        for dzien_obj in self.obj_miesiac.dni:
            stan = dzien_obj.pobierz_zmiane(pracownik.db_id)
            if stan == "UUW":
                suma_godzin += pracownik.norma_dobowa(self.norma_miesiaca)
            elif stan in ["D", "N"]:
                suma_godzin += 12.0
            elif stan == "M":
                suma_godzin += 8.0
            elif stan == "4":
                suma_godzin += 4.0

        pracownik.wyrobione_godziny = suma_godzin
        norma_pracownika = pracownik.get_norma_miesiaca(self.norma_miesiaca)

        suma_str = f"{int(suma_godzin)}" if suma_godzin.is_integer() else f"{suma_godzin:.1f}"
        norma_str = f"{int(norma_pracownika)}" if norma_pracownika.is_integer() else f"{norma_pracownika:.1f}"

        stany = self._zlicz_stany(pracownik)
        stany_str = f"D:{stany['D']} | N:{stany['N']} | U:{stany['UUW']} | M:{stany['M']} | 4:{stany['4']} | L:{stany['L4']} | X:{stany['X']}"

        tekst = f"{suma_str}/{norma_str}h \n{stany_str}"
        if pracownik in self.etykiety_sum:
            self.etykiety_sum[pracownik].configure(text=tekst)

    def _przelicz_dzien(self, dzien_obj: DzienPracy):
        pracownicy_mapa = {p.db_id: p for p in self.pracownicy}
        obstawione_godziny = dzien_obj.oblicz_obstawienie_godzin(pracownicy_mapa, self.norma_miesiaca)

        stany = {"D": 0, "N": 0, "UUW": 0, "M": 0, "4": 0, "L4": 0}
        for p in self.pracownicy:
            stan = dzien_obj.pobierz_zmiane(p.db_id)
            if stan in stany:
                stany[stan] += 1

        wymagane_godziny = 24.0
        obs_str = f"{int(obstawione_godziny)}" if obstawione_godziny.is_integer() else f"{obstawione_godziny:.1f}"
        wym_str = f"{int(wymagane_godziny)}" if wymagane_godziny.is_integer() else f"{wymagane_godziny:.1f}"

        stany_str = f"D:{stany['D']} N:{stany['N']}\nM:{stany['M']} 4:{stany['4']}"
        tekst = f"{obs_str}/{wym_str}h\n---\n{stany_str}"

        if stany['D'] > 1 or stany['N'] > 1 or obstawione_godziny > wymagane_godziny:
            kolor = "#B2001E"
        elif obstawione_godziny == wymagane_godziny:
            kolor = "#2ea043"
        elif obstawione_godziny < wymagane_godziny:
            kolor = "#d97706"
        else:
            kolor = "gray"

        if dzien_obj in self.etykiety_sum_dni:
            self.etykiety_sum_dni[dzien_obj].configure(text=tekst, text_color=kolor)

    def _aktualizuj_stan(self, pracownik: Pracownik, dzien_obj: DzienPracy):
        for (r, c), (p, d) in self.dane_pól.items():
            if p == pracownik and d == dzien_obj:
                nowy_stan = self.pola[(r, c)].get()
                dzien_obj.ustaw_zmiane(pracownik.db_id, nowy_stan)
                break

        self._przelicz_pracownika(pracownik)
        self._przelicz_dzien(dzien_obj)

    def przelicz_sumy(self):
        for p in self.pracownicy:
            self._przelicz_pracownika(p)
        for d in self.obj_miesiac.dni:
            self._przelicz_dzien(d)

    def _zmiana_daty(self, *args):
        try:
            self.zapisz_do_excela()
            self.wybrany_rok = int(self.rok_entry.get())
            self.wybrany_miesiac = int(self.miesiac_option.get())
            self.obj_miesiac = Miesiac(self.wybrany_rok, self.wybrany_miesiac, self.norma_miesiaca)
            self._wygeneruj_tabele()
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawny rok.", parent=self)

    def wczytaj_z_excela(self):
        filename = f"grafiki/grafik_stany_{self.wybrany_rok}_{self.wybrany_miesiac:02d}.xlsx"
        if not os.path.exists(filename):
            for (r, c), (prac, dzien_obj) in self.dane_pól.items():
                dzien_obj.ustaw_zmiane(prac.db_id, "P")
                self._odswiez_kolor_komorki(r, c)
            return

        try:
            df = pd.read_excel(filename, dtype=str)
            for (r, c), (prac, dzien_obj) in self.dane_pól.items():
                naglowek_excel = f"{dzien_obj.data.day:02d}.{dzien_obj.data.month:02d} ({dzien_obj.dzien_tyg})"
                wiersz_prac = df[(df["Imię"] == prac.imie) & (df["Nazwisko"] == prac.nazwisko)]

                stan = "P"
                if not wiersz_prac.empty and naglowek_excel in df.columns:
                    wartosc = wiersz_prac.iloc[0][naglowek_excel]
                    if pd.notna(wartosc) and str(wartosc).strip() in self.STATUSY:
                        stan = str(wartosc).strip()

                self.pola[(r, c)].set(stan)
                dzien_obj.ustaw_zmiane(prac.db_id, stan)
                self._odswiez_kolor_komorki(r, c)

        except Exception as e:
            messagebox.showerror("Błąd odczytu", f"Nie udało się wczytać grafiku z Excela:\n{e}", parent=self)

    def zapisz_do_excela(self):
        self.przelicz_sumy()

        rows = []
        for p in self.pracownicy:
            stany = self._zlicz_stany(p)
            row_data = {
                "Imię": p.imie,
                "Nazwisko": p.nazwisko,
                "Etat": p.etat,
                "Norma (h)": p.get_norma_miesiaca(self.norma_miesiaca),
                "Dni pracy": p.dni_pracy_str()
            }
            for dzien_obj in self.obj_miesiac.dni:
                naglowek_excel = f"{dzien_obj.data.day:02d}.{dzien_obj.data.month:02d} ({dzien_obj.dzien_tyg})"
                row_data[naglowek_excel] = dzien_obj.pobierz_zmiane(p.db_id)

            row_data["Suma godz."] = p.wyrobione_godziny
            row_data["Bilans (h)"] = p.roznica_godzin(self.norma_miesiaca)
            row_data["D"] = stany["D"]
            row_data["N"] = stany["N"]
            row_data["UUW"] = stany["UUW"]
            row_data["L4"] = stany["L4"]
            row_data["M"] = stany["M"]
            row_data["4"] = stany["4"]
            row_data["X"] = stany["X"]
            rows.append(row_data)

        row_dzien_sum = {
            "Imię": "PODSUMOWANIE",
            "Nazwisko": "",
            "Etat": "",
            "Norma (h)": "",
            "Dni pracy": ""
        }

        pracownicy_mapa = {p.db_id: p for p in self.pracownicy}
        for dzien_obj in self.obj_miesiac.dni:
            obstawione = dzien_obj.oblicz_obstawienie_godzin(pracownicy_mapa, self.norma_miesiaca)
            naglowek_excel = f"{dzien_obj.data.day:02d}.{dzien_obj.data.month:02d} ({dzien_obj.dzien_tyg})"
            row_dzien_sum[naglowek_excel] = obstawione

        rows.append(row_dzien_sum)

        df = pd.DataFrame(rows)
        filename = f"grafiki/grafik_stany_{self.wybrany_rok}_{self.wybrany_miesiac:02d}.xlsx"

        try:
            df.to_excel(filename, index=False, engine="openpyxl")
        except ModuleNotFoundError:
            messagebox.showerror(
                "Brak biblioteki",
                "Brak wymaganej biblioteki 'openpyxl'.\nZainstaluj ją wpisując w terminalu:\npip install openpyxl",
                parent=self
            )
        except PermissionError:
            messagebox.showerror(
                "Błąd dostępu",
                f"Plik '{filename}' jest obecnie otwarty w innym programie (np. MS Excel).\nZamknij go i spróbuj ponownie.",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Błąd podczas zapisu do Excela: {e}", parent=self)

    def automatycznie_generuj_grafik(self):
        if not self.pracownicy:
            messagebox.showwarning("Brak pracowników", "Dodaj najpierw pracowników do bazy!", parent=self)
            return

        for (r, c), (pracownik, dzien_obj) in self.dane_pól.items():
            status_z_gui = self.pola[(r, c)].get()
            dzien_obj.ustaw_zmiane(pracownik.db_id, status_z_gui)

        generator = GeneratorGrafiku(self.obj_miesiac, self.pracownicy, self.norma_miesiaca)
        generator.generuj()

        for (r, c), (pracownik, dzien_obj) in self.dane_pól.items():
            nowy_status = dzien_obj.pobierz_zmiane(pracownik.db_id)
            self.pola[(r, c)].set(nowy_status)
            self._odswiez_kolor_komorki(r, c)

        self.przelicz_sumy()
        messagebox.showinfo("Sukces", "Dokończono układanie grafiku!", parent=self)


if __name__ == "__main__":
    app = TabelaGrafikApp()
    app.mainloop()
