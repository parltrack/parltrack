from sqlalchemy import (
    create_engine,
    Column,
    Integer,
)
from json import dumps
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql.expression import cast
from config import SQLALCHEMY_DATABASE_URI, DB_DEBUG

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()

def json_serializer(o):
    return dumps(o, default=dateJSONhandler)

engine = create_engine(SQLALCHEMY_DATABASE_URI,
                       echo=DB_DEBUG,
                       json_serializer=json_serializer)
session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))
Base = declarative_base()
Base.query = session.query_property()


class Dossier(Base):
    __tablename__ = 'dossier'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)


class Mep(Base):
    __tablename__ = 'mep'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)

    @staticmethod
    def get_by_id(id):
        if not id:
            return None
        try:
            return session.query(Mep).filter(Mep.data['UserID'].astext == str(id)).first()
        except Exception as e:
            print(e)
            session.rollback()

    @staticmethod
    def upsert(mep_data):
        mep_id = mep_data.get('UserID')
        mep = Mep.get_by_id(mep_id)
        if mep:
            mep.data = mep_data
        else:
            mep = Mep(id=mep_id, data=mep_data)
        session.add(mep)
        session.commit()
        return mep


class Vote(Base):
    __tablename__ = 'vote'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)


class Meeting(Base):
    __tablename__ = 'meeting'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)


class Amendment(Base):
    __tablename__ = 'amendment'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)


if __name__ == '__main__':
    print("Creating database")
    try:
        Base.metadata.create_all(engine, checkfirst=True)
        print("Database created")
    except Exception as e:
        print("[E] Failed to create database: {0}".format(e))
