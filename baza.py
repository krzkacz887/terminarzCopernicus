import calendar
import datetime
import sqlite3
import pandas as pd

DB_NAME = "grafik.db"


def init_db():
    """Tworzy bazę danych i tabelę pracowników z obsługą migracji."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pracownicy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imie TEXT NOT NULL,
            nazwisko TEXT NOT NULL,
            etat REAL DEFAULT 1.0,
            dni_pracy TEXT DEFAULT '1:DN,2:DN,3:DN,4:DN,5:DN,6:DN,7:DN,8:DN,9:DN,10:DN,11:DN,12:DN,13:DN,14:DN,15:DN,16:DN,17:DN,18:DN,19:DN,20:DN,21:DN,22:DN,23:DN,24:DN,25:DN,26:DN,27:DN,28:DN,29:DN,30:DN,31:DN',
            pref_dni_tyg TEXT DEFAULT '',
            pref_pora_dnia TEXT DEFAULT ''
        )
    """)
    cursor.execute("PRAGMA table_info(pracownicy)")
    columns = [col[1] for col in cursor.fetchall()]

    if "dni_pracy" not in columns:
        cursor.execute("ALTER TABLE pracownicy ADD COLUMN dni_pracy TEXT DEFAULT ''")
    if "pref_dni_tyg" not in columns:
        cursor.execute("ALTER TABLE pracownicy ADD COLUMN pref_dni_tyg TEXT DEFAULT ''")
    if "pref_pora_dnia" not in columns:
        cursor.execute("ALTER TABLE pracownicy ADD COLUMN pref_pora_dnia TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def db_dodaj_pracownika(imie, nazwisko, etat, dni_pracy, pref_dni_tyg=""):
    """
    Dodaje pracownika do bazy.
    dni_pracy przyjmuje tekst w formacie: "1:DN,2:D,3:N"
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pracownicy (imie, nazwisko, etat, dni_pracy, pref_dni_tyg, pref_pora_dnia)
        VALUES (?, ?, ?, ?, ?, '')
    """, (imie, nazwisko, etat, dni_pracy, pref_dni_tyg))
    conn.commit()
    conn.close()


def db_aktualizuj_pracownika(db_id, imie, nazwisko, etat, dni_pracy, pref_dni_tyg=""):
    """
    Aktualizuje dane pracownika w bazie.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE pracownicy 
        SET imie=?, nazwisko=?, etat=?, dni_pracy=?, pref_dni_tyg=?, pref_pora_dnia='' 
        WHERE id=?
    """, (imie, nazwisko, etat, dni_pracy, pref_dni_tyg, db_id))
    conn.commit()
    conn.close()


def db_pobierz_pracownikow():
    """Pobiera wszystkich pracowników z bazy danych."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, imie, nazwisko, etat, dni_pracy, pref_dni_tyg FROM pracownicy")
    rows = cursor.fetchall()
    conn.close()

    pracownicy = []
    for row in rows:
        p = Pracownik(
            db_id=row[0],
            imie=row[1],
            nazwisko=row[2],
            etat=row[3],
            dni_pracy=row[4] or "",
            pref_dni_tyg=row[5] or ""
        )
        pracownicy.append(p)

    return pracownicy


def db_usun_pracownika(db_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pracownicy WHERE id = ?", (db_id,))
    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Wczytywanie dostępności z pliku CSV
# ------------------------------------------------------------------

def normalizuj_kody_pory(wartosc_str: str) -> str:
    """Konwertuje dowolne oznaczenie z CSV na ujednolicony kod: 'D', 'N', 'DN' lub '' (brak)."""
    val = str(wartosc_str).strip().upper()
    if val in ["D", "DZIEŃ", "DZIEN", "DAY"]:
        return "D"
    elif val in ["N", "NOC", "NIGHT"]:
        return "N"
    elif val in ["DN", "D+N", "D,N", "D/N", "DOWOLNA", "OBIE", "ALL", "1"]:
        return "DN"
    return ""


def wczytaj_dostepnosc_z_csv(filepath: str, rok: int = None, miesiac: int = None) -> dict:
    """Odczytuje plik CSV i zwraca słownik dostępności w formacie: {dzien_int: kod_pory_str}.

    Dni nieopisane w pliku CSV otrzymują status 'BRAK'.
    """
    dostepnosc_z_pliku = {}
    try:
        df = pd.read_csv(
            filepath,
            sep=r'[\s;,|\t]+',
            engine="python",
            encoding="utf-8-sig",
            dtype=str,
        )

        df.columns = [str(c).strip().lower() for c in df.columns]

        # 1. Szukanie odpowiednich kolumn
        col_dzien = next(
            (c for c in df.columns if c in ["dzien", "dzień", "day", "dni", "data", "date"]),
            None,
        )
        col_pora = next(
            (c for c in df.columns if c in ["pora", "pora_dnia", "pora dnia", "zmiana", "shift", "dostepnosc", "status"]),
            None,
        )

        # 2. Awaryjne przypisanie pierwszych dwóch kolumn
        if not col_dzien or not col_pora:
            if len(df.columns) >= 2:
                col_dzien, col_pora = df.columns[0], df.columns[1]
            else:
                raise ValueError("Nie udało się rozpoznać 2 kolumn. Sprawdź separator pliku CSV.")

        # 3. Przetwarzanie wierszy z pliku CSV
        for _, row in df.iterrows():
            val_d = str(row[col_dzien]).strip()
            val_p = str(row[col_pora]).strip()

            if not val_d or val_d.lower() == "nan":
                continue

            try:
                if "-" in val_d:
                    d_int = datetime.datetime.strptime(val_d, "%Y-%m-%d").day
                else:
                    d_int = int(float(val_d))

                kod = normalizuj_kody_pory(val_p)

                if 1 <= d_int <= 31:
                    # Jeśli zdeklarowano konkretny kod
                    if kod:
                        if d_int in dostepnosc_z_pliku and dostepnosc_z_pliku[d_int] != "BRAK":
                            dostepnosc_z_pliku[d_int] = normalizuj_kody_pory(dostepnosc_z_pliku[d_int] + kod)
                        else:
                            dostepnosc_z_pliku[d_int] = kod
                    else:
                        dostepnosc_z_pliku[d_int] = "BRAK"
            except (ValueError, KeyError):
                continue

    except Exception as e:
        raise RuntimeError(f"Błąd podczas parsowania CSV: {e}")

    # --- Wypełnianie brakujących dni jako 'BRAK' ---
    max_dni = 31
    if rok and miesiac:
        max_dni = calendar.monthrange(rok, miesiac)[1]

    pelna_dostepnosc = {}
    for d in range(1, max_dni + 1):
        # Jeśli dnia nie ma w pliku CSV lub kod był pusty -> BRAK
        pelna_dostepnosc[d] = dostepnosc_z_pliku.get(d, "BRAK")

    return pelna_dostepnosc
# ------------------------------------------------------------------
# Klasy modelu danych
# ------------------------------------------------------------------

class Pracownik:
    DNI_NAZWY = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]

    def __init__(self, imie, nazwisko, etat=1.0, dni_pracy="", pref_dni_tyg="", pref_pora_dnia="", db_id=None):
        self.db_id = db_id
        self.imie = imie
        self.nazwisko = nazwisko
        self.etat = float(etat)
        self.wyrobione_godziny = 0.0
        self.dni_pracy = self._parsuj_dni_pracy(dni_pracy)

        # Preferowane dni tygodnia (0-6 -> Pn-Nd)
        if isinstance(pref_dni_tyg, str) and pref_dni_tyg.strip():
            self.pref_dni_tyg = {int(d.strip()) for d in pref_dni_tyg.split(",") if d.strip().isdigit()}
        elif isinstance(pref_dni_tyg, (set, list)):
            self.pref_dni_tyg = {int(d) for d in pref_dni_tyg}
        else:
            self.pref_dni_tyg = set()

    def _parsuj_dni_pracy(self, dni_pracy_input) -> dict:
        mapa = {}

        if isinstance(dni_pracy_input, dict):
            return {int(k): (str(v).upper() if str(v).strip() else "BRAK") for k, v in dni_pracy_input.items()}

        if isinstance(dni_pracy_input, str) and dni_pracy_input.strip():
            elementy = dni_pracy_input.split(",")
            for item in elementy:
                item_str = item.strip()
                if ":" in item_str:
                    d_str, p_str = item_str.split(":", 1)
                    if d_str.isdigit():
                        p_val = p_str.upper().strip()
                        mapa[int(d_str)] = p_val if p_val else "BRAK"
                elif item_str.isdigit():
                    mapa[int(item_str)] = "DN"
        elif isinstance(dni_pracy_input, (set, list, tuple)):
            for d in dni_pracy_input:
                try:
                    mapa[int(d)] = "DN"
                except ValueError:
                    pass
        else:
            mapa = {d: "DN" for d in range(1, 32)}

        return mapa

    def dni_pracy_str(self) -> str:
        """Generuje reprezentację tekstową słownika dostępności do zapisu w bazie danych (np. '1:DN,2:D,3:N')."""
        skladniki = []
        for d in sorted(self.dni_pracy.keys()):
            skladniki.append(f"{d}:{self.dni_pracy[d]}")
        return ",".join(skladniki)

    def get_norma_miesiaca(self, norma_bazy_miesiaca: float) -> float:
        return self.etat * norma_bazy_miesiaca

    @property
    def pelne_nazwisko(self):
        return f"{self.imie} {self.nazwisko}"

    def norma_dobowa(self, norma_bazy_miesiaca: float, dni_robocze: int) -> float:
        if dni_robocze <= 0:
            return 0.0
        return self.get_norma_miesiaca(norma_bazy_miesiaca) / float(dni_robocze)

    def roznica_godzin(self, norma_bazy_miesiaca: float) -> float:
        return self.wyrobione_godziny - self.get_norma_miesiaca(norma_bazy_miesiaca)

    def moze_pracowac_w_dzien(self, data_lub_dzien, pora: str = None) -> bool:
        dzien_num = data_lub_dzien.day if hasattr(data_lub_dzien, "day") else int(data_lub_dzien)

        if not isinstance(self.dni_pracy, dict) or dzien_num not in self.dni_pracy:
            return False

        dostepna_pora = self.dni_pracy[dzien_num]

        if dostepna_pora == "BRAK":
            return False

        if pora is None:
            return dostepna_pora in ("DN", "D", "N")
        if pora == "D":
            return dostepna_pora in ("D", "DN")
        if pora == "N":
            return dostepna_pora in ("N", "DN")

        return False

    def pref_dni_tyg_str(self) -> str:
        return ",".join(map(str, sorted(self.pref_dni_tyg)))


class DzienPracy:
    dni_tygodnia_pl = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]

    def __init__(self, data: datetime.date):
        self.data = data
        self.dzien_tyg = self.dni_tygodnia_pl[data.weekday()]
        self.czy_roboczy = data.weekday() < 5
        self.przydzialy_pracownikow = {}
        self.oblozenie_godzin = 0
        self.czy_swieto = False

    @property
    def sformatowany_dzien(self):
        return f"{self.data.day:02d}\n{self.dzien_tyg}"

    def ustaw_zmiane(self, pracownik_id, status: str):
        self.przydzialy_pracownikow[pracownik_id] = status

    def zmien_swieta(self):
        self.czy_swieto = False if self.czy_swieto else True

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

    def __init__(self, rok: int, miesiac: int, norma_miesiaca: float = None):
        self.rok = rok
        self.miesiac = miesiac
        self.dni = self._wygeneruj_dni()

        if norma_miesiaca is None:
            self.norma_miesiaca = float(self.liczba_dni_roboczych * 8)
        else:
            self.norma_miesiaca = float(norma_miesiaca)

    def _wygeneruj_dni(self):
        liczba_dni = calendar.monthrange(self.rok, self.miesiac)[1]
        return [
            DzienPracy(datetime.date(self.rok, self.miesiac, d))
            for d in range(1, liczba_dni + 1)
        ]
    @property
    def liczba_dni_roboczych(self) -> int:
        """Zwraca liczbę dni roboczych (od poniedziałku do piątku) w miesiącu."""
        return sum(1 for d in self.dni if d.czy_roboczy and not d.czy_swieto)
    @property
    def liczba_dni_wolnych(self) -> int:
        """Zwraca liczbę dni wolnych od pracy (soboty i niedziele)."""
        return sum(1 for d in self.dni if not d.czy_roboczy)
    @property
    def liczba_dni(self) -> int:
        """Zwraca całkowitą liczbę dni w miesiącu (np. 28, 30, 31)."""
        return len(self.dni)
