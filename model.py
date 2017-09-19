from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    JSON,
)
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config import SQLALCHEMY_DATABASE_URI

engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=True)
session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))
Base = declarative_base()
Base.query = session.query_property()


class Dossier(Base):
    __tablename__ = 'dossier'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)

    def __init__(self, dossier_json):
        self.data = dossier_json


class Mep(Base):
    __tablename__ = 'mep'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)

    def __init__(self, mep_json):
        self.data = mep_json


class Vote(Base):
    __tablename__ = 'vote'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)

    def __init__(self, vote_json):
        self.data = vote_json


class Meeting(Base):
    __tablename__ = 'meeting'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)

    def __init__(self, meetin_json):
        self.data = meeting_json


class Amendment(Base):
    __tablename__ = 'amendment'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)

    def __init__(self, amendment_json):
        self.data = amendment_json


if __name__ == '__main__':
    print("Creating database")
    try:
        Base.metadata.create_all(engine, checkfirst=True)
        print("Database created")
    except Exception as e:
        print("[E] Failed to create database: {0}".format(e))
