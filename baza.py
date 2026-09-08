import calendar
import datetime
import sqlite3

DB_NAME = "grafik.db"


def init_db():
    """Tworzy bazę danych i tabelę pracowników z pełną obsługą preferencji oraz migracji."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pracownicy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imie TEXT NOT NULL,
            nazwisko TEXT NOT NULL,
            etat REAL DEFAULT 1.0,
            dni_pracy TEXT DEFAULT '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31',
            pref_dni_tyg TEXT DEFAULT '',
            pref_pora_dnia TEXT DEFAULT ''
        )
    """)

    # Migracje dla istniejących baz bez nowszych kolumn
    cursor.execute("PRAGMA table_info(pracownicy)")
    columns = [col[1] for col in cursor.fetchall()]

    if "dni_pracy" not in columns:
        cursor.execute(
            "ALTER TABLE pracownicy ADD COLUMN dni_pracy TEXT DEFAULT"
            " '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31'"
        )
    if "pref_dni_tyg" not in columns:
        cursor.execute(
            "ALTER TABLE pracownicy ADD COLUMN pref_dni_tyg TEXT DEFAULT ''"
        )
    if "pref_pora_dnia" not in columns:
        cursor.execute(
            "ALTER TABLE pracownicy ADD COLUMN pref_pora_dnia TEXT DEFAULT ''"
        )

    conn.commit()
    conn.close()


def db_dodaj_pracownika(
    imie, nazwisko, etat, dni_pracy, pref_dni_tyg="", pref_pora_dnia=""
):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pracownicy (imie, nazwisko, etat, dni_pracy, pref_dni_tyg, pref_pora_dnia)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (imie, nazwisko, etat, dni_pracy, pref_dni_tyg, pref_pora_dnia),
    )
    conn.commit()
    conn.close()


def db_aktualizuj_pracownika(
    db_id, imie, nazwisko, etat, dni_pracy, pref_dni_tyg="", pref_pora_dnia=""
):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE pracownicy 
        SET imie=?, nazwisko=?, etat=?, dni_pracy=?, pref_dni_tyg=?, pref_pora_dnia=? 
        WHERE id=?
    """,
        (imie, nazwisko, etat, dni_pracy, pref_dni_tyg, pref_pora_dnia, db_id),
    )
    conn.commit()
    conn.close()


def db_pobierz_pracownikow():
    """Pobiera wszystkich pracowników z bazy danych i zwraca je jako obiekty klasy Pracownik."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, imie, nazwisko, etat, dni_pracy, pref_dni_tyg,"
        " pref_pora_dnia FROM pracownicy"
    )
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
            pref_dni_tyg=row[5] or "",
            pref_pora_dnia=row[6] or "",
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


class Pracownik:
    DNI_NAZWY = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]

    def __init__(
        self,
        imie,
        nazwisko,
        etat=1.0,
        dni_pracy="",
        pref_dni_tyg="",
        pref_pora_dnia="",
        db_id=None,
    ):
        self.db_id = db_id
        self.imie = imie
        self.nazwisko = nazwisko
        self.etat = float(etat)
        self.wyrobione_godziny = 0.0

        # Dni miesiąca (1-31)
        if isinstance(dni_pracy, str) and dni_pracy.strip():
            try:
                self.dni_pracy = {
                    int(d.strip())
                    for d in dni_pracy.split(",")
                    if d.strip().isdigit()
                }
            except ValueError:
                self.dni_pracy = set(range(1, 32))
        elif isinstance(dni_pracy, (set, list)):
            self.dni_pracy = {int(d) for d in dni_pracy}
        else:
            self.dni_pracy = set(range(1, 32))

        # Preferowane dni tygodnia (0-6 -> Pn-Nd)
        if isinstance(pref_dni_tyg, str) and pref_dni_tyg.strip():
            self.pref_dni_tyg = {
                int(d.strip())
                for d in pref_dni_tyg.split(",")
                if d.strip().isdigit()
            }
        elif isinstance(pref_dni_tyg, (set, list)):
            self.pref_dni_tyg = {int(d) for d in pref_dni_tyg}
        else:
            self.pref_dni_tyg = set()

        # Preferowana pora dnia ("D", "N" lub "")
        self.pref_pora_dnia = pref_pora_dnia or ""

    def get_norma_miesiaca(self, norma_bazy_miesiaca: float) -> float:
        return self.etat * norma_bazy_miesiaca

    @property
    def pelne_nazwisko(self):
        return f"{self.imie} {self.nazwisko}"

    def norma_dobowa(self, norma_bazy_miesiaca: float) -> float:
        return self.get_norma_miesiaca(norma_bazy_miesiaca) / 20.0

    def roznica_godzin(self, norma_bazy_miesiaca: float) -> float:
        return (
            self.wyrobione_godziny - self.get_norma_miesiaca(norma_bazy_miesiaca)
        )

    def moze_pracowac_w_dzien(self, data: datetime.date) -> bool:
        return data.day in self.dni_pracy

    def dni_pracy_str(self) -> str:
        return ",".join(map(str, sorted(list(self.dni_pracy))))

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

    @property
    def sformatowany_dzien(self):
        return f"{self.data.day:02d}\n{self.dzien_tyg}"

    def ustaw_zmiane(self, pracownik_id, status: str):
        self.przydzialy_pracownikow[pracownik_id] = status

    def pobierz_zmiane(self, pracownik_id, domyslna="P") -> str:
        return self.przydzialy_pracownikow.get(pracownik_id, domyslna)

    def oblicz_obstawienie_godzin(
        self, pracownicy_mapa, norma_miesiaca: float
    ) -> float:
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
