
from datetime import date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    backref,
    relationship,
    scoped_session,
    sessionmaker,
)
from sqlalchemy.sql.expression import cast

from config import NOTIF_DB_URI, DB_DEBUG

engine = create_engine(NOTIF_DB_URI, echo=DB_DEBUG)
session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))
Base = declarative_base()
Base.query = session.query_property()


class Subscriber(Base):
    __tablename__ = 'subscriber'

    email = Column(String(64), unique=True, primary_key=True)
    activation_key = Column(String(64))
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship('Group', foreign_keys=[group_id], backref="subscribers", cascade="all, delete-orphan", single_parent=True)
    added = Column(Date, default=date.today)

    def __unicode__(self):
        return '%s [%s]' % (self.email, 'active' if not self.activation_key else 'inactive')

    def __repr__(self):
        return repr(self.__unicode__())


class Item(Base):
    __tablename__ = 'item'

    name = Column(String(64), unique=True, primary_key=True)
    type = Column(String(64))
    activation_key = Column(String(64))
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship('Group', foreign_keys=[group_id], backref="items", cascade="all, delete-orphan", single_parent=True)
    added = Column(Date, default=date.today)


    def __unicode__(self):
        return '%s:%s [%s]' % (self.type, self.name, 'active' if not self.activation_key else 'inactive')

    def __repr__(self):
        return repr(self.__unicode__())


class Group(Base):
    __tablename__ = 'group'

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    activation_key = Column(String(64))

    def __unicode__(self):
        return '%s (%s) - subscribers: {%s} items {%s}' % (
            self.name,
            'active' if not self.activation_key else 'inactive',
            ', '.join(map(str, self.subscribers)),
            ', '.join(map(str, self.items)),
        )

    def __repr__(self):
        return repr(self.__unicode__())


if __name__ == '__main__':
    print("Creating database")
    try:
        Base.metadata.create_all(engine, checkfirst=True)
        print("Database created")
        from IPython import embed; embed()
    except Exception as e:
        print("[E] Failed to create database: {0}".format(e))
