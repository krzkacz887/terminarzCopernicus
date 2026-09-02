import os
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = "sqlite:///grafik.db"

Engine = create_engine(DB_PATH, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=Engine)


class PracownikDB(Base):
    __tablename__ = "pracownicy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    imie = Column(String, nullable=False)
    nazwisko = Column(String, nullable=False)
    etat = Column(Float, default=1.0)


# Tworzenie bazy i tabeli przy pierwszym uruchomieniu
Base.metadata.create_all(Engine)


class BazaManager:
    @staticmethod
    def pobierz_wszystkich():
        db = SessionLocal()
        try:
            return db.query(PracownikDB).all()
        finally:
            db.close()

    @staticmethod
    def dodaj_pracownika(imie: str, nazwisko: str, etat: float = 1.0):
        db = SessionLocal()
        try:
            nowy = PracownikDB(imie=imie, nazwisko=nazwisko, etat=etat)
            db.add(nowy)
            db.commit()
            db.refresh(nowy)
            return nowy
        finally:
            db.close()

    @staticmethod
    def usun_pracownika(imie: str, nazwisko: str):
        db = SessionLocal()
        try:
            pracownik = db.query(PracownikDB).filter(
                PracownikDB.imie == imie,
                PracownikDB.nazwisko == nazwisko
            ).first()
            if pracownik:
                db.delete(pracownik)
                db.commit()
                return True
            return False
        finally:
            db.close()
