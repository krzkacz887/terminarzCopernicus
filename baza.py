import calendar
import datetime
import os
import customtkinter as ctk
import pandas as pd
from tkinter import ttk, messagebox, simpledialog

import sqlite3

DB_NAME = "grafik.db"

def init_db():
    """Tworzy bazę danych i tabelę pracowników z pełną obsługą dni pracy."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pracownicy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imie TEXT NOT NULL,
            nazwisko TEXT NOT NULL,
            etat REAL DEFAULT 1.0,
            dni_pracy TEXT DEFAULT '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31'
        )
    """)

    # Migracja dla istniejących baz bez kolumny dni_pracy
    cursor.execute("PRAGMA table_info(pracownicy)")
    columns = [col[1] for col in cursor.fetchall()]
    if "dni_pracy" not in columns:
        cursor.execute("ALTER TABLE pracownicy ADD COLUMN dni_pracy TEXT DEFAULT '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31'")

    conn.commit()
    conn.close()

def db_pobierz_pracownikow():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, imie, nazwisko, etat, dni_pracy FROM pracownicy")
    rows = cursor.fetchall()
    conn.close()
    return rows

def db_dodaj_pracownika(imie, nazwisko, etat, dni_pracy=""):
    if not dni_pracy:
        dni_pracy = ",".join(map(str, range(1, 32)))
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pracownicy (imie, nazwisko, etat, dni_pracy) VALUES (?, ?, ?, ?)",
        (imie, nazwisko, etat, dni_pracy)
    )
    conn.commit()
    conn.close()

def db_aktualizuj_pracownika(db_id, imie, nazwisko, etat, dni_pracy):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pracownicy SET imie = ?, nazwisko = ?, etat = ?, dni_pracy = ? WHERE id = ?",
        (imie, nazwisko, etat, dni_pracy, db_id)
    )
    conn.commit()
    conn.close()

def db_usun_pracownika(db_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pracownicy WHERE id = ?", (db_id,))
    conn.commit()
    conn.close()

# ------------------------------------------------------------------

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class Pracownik:
    DNI_NAZWY = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]

    def __init__(self, imie, nazwisko, etat=1.0, dni_pracy="", db_id=None):
        self.db_id = db_id
        self.imie = imie
        self.nazwisko = nazwisko
        self.etat = float(etat)
        self.wyrobione_godziny = 0.0
        # Zbiór numerów dni miesiąca (np. {1, 2, 15, 20})
        if dni_pracy:
            try:
                self.dni_pracy = set(map(int, [d.strip() for d in dni_pracy.split(",") if d.strip()]))
            except ValueError:
                self.dni_pracy = set(range(1, 32))
        else:
            self.dni_pracy = set(range(1, 32))

    def get_norma_miesiaca(self, norma_bazy_miesiaca: float) -> float:
        return self.etat * norma_bazy_miesiaca

    @property
    def pelne_nazwisko(self):
        return f"{self.imie} {self.nazwisko}"

    def norma_dobowa(self, norma_bazy_miesiaca: float) -> float:
        return self.get_norma_miesiaca(norma_bazy_miesiaca) / 20.0

    def roznica_godzin(self, norma_bazy_miesiaca: float) -> float:
        return self.wyrobione_godziny - self.get_norma_miesiaca(norma_bazy_miesiaca)

    def moze_pracowac_w_dzien(self, data: datetime.date) -> bool:
        return data.day in self.dni_pracy

    def dni_pracy_str(self) -> str:
        return ",".join(map(str, sorted(list(self.dni_pracy))))



class DzienPracy:
    dni_tygodnia_pl = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]

    def __init__(self, data: datetime.date):
        self.data = data
        self.dzien_tyg = self.dni_tygodnia_pl[data.weekday()]
        self.czy_roboczy = data.weekday() < 5
        self.przydzialy_pracownikow = {}
        self.oblozenie_godzin = 0

    @property
    def sformatowany_dzien(self):
        return f"{self.data.day:02d}\n{self.dzien_tyg}"

    def ustaw_zmiane(self, pracownik_id, status: str):
        self.przydzialy_pracownikow[pracownik_id] = status

    def pobierz_zmiane(self, pracownik_id, domyslna="P") -> str:
        return self.przydzialy_pracownikow.get(pracownik_id, domyslna)

    def oblicz_obstawienie_godzin(self, pracownicy_mapa, norma_miesiaca: float) -> float:
        godziny = 0.0
        for p_id, status in self.przydzialy_pracownikow.items():
            if status in ["D", "N"]:
                godziny += 12.0
            elif status == "M":
                godziny += 8.0
            elif status == "4":
                godziny += 4.0
        self.oblozenie_godzin = godziny
        return godziny


class Miesiac:
    def __init__(self, rok: int, miesiac: int, norma_miesiaca: float = 160.0):
        self.rok = rok
        self.miesiac = miesiac
        self.norma_miesiaca = norma_miesiaca
        self.dni = self._wygeneruj_dni()

    def _wygeneruj_dni(self):
        liczba_dni = calendar.monthrange(self.rok, self.miesiac)[1]
        return [
            DzienPracy(datetime.date(self.rok, self.miesiac, d))
            for d in range(1, liczba_dni + 1)
        ]
